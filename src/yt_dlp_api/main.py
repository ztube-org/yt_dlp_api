import asyncio
import os
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.parse import quote, urljoin, urlparse

import httpx
from asyncache import cached
from cachetools import TTLCache
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

app = FastAPI(title="yt-dlp API", version="0.1.0")

_raw_api_key = os.getenv("YT_DLP_API_KEY")
API_KEY = _raw_api_key.strip() if _raw_api_key and _raw_api_key.strip() else None


DESIRED_VIDEO_FORMAT_IDS: tuple[str, ...] = ("134", "135", "136", "137", "298", "299")
DESIRED_M3U8_FORMAT_IDS: tuple[str, ...] = ("93", "94", "95", "96", "300", "301")
DESIRED_AUDIO_FORMAT_ID = "140"


_PROXY_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


class StreamInfo(BaseModel):
    format_id: str
    ext: str
    url: str
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate: float | None = None
    filesize: int | None = None
    filesize_approx: int | None = None
    proxied_url: str | None = None


class VideoDetailResponse(BaseModel):
    id: str
    title: str
    duration: int | None = None
    uploader: str | None = None
    channel_id: str | None = None
    video_formats: Sequence[StreamInfo] = ()
    m3u8_formats: Sequence[StreamInfo] = ()
    audio_format: StreamInfo | None = None


class PlaylistVideoSummary(BaseModel):
    id: str
    title: str
    duration: int | None = None
    uploader: str | None = None
    channel_id: str | None = None


class PlaylistDetailResponse(BaseModel):
    id: str
    title: str | None = None
    uploader: str | None = None
    channel_id: str | None = None
    video_count: int = 0
    videos: Sequence[PlaylistVideoSummary] = ()


VIDEO_INFO_CACHE = TTLCache(maxsize=1024, ttl=3600)
PLAYLIST_INFO_CACHE = TTLCache(maxsize=1024, ttl=1800)


API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)


async def enforce_api_key(authorization: str | None = Security(API_KEY_HEADER)) -> None:
    if API_KEY is None:
        return
    if authorization == API_KEY:
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health", summary="Health check", tags=["system"])
def read_health() -> Mapping[str, Any]:
    return {
        "status": "ok",
        "video_cache": {
            "size": len(VIDEO_INFO_CACHE),
            "maxsize": VIDEO_INFO_CACHE.maxsize,
            "ttl_seconds": VIDEO_INFO_CACHE.ttl,
        },
        "playlist_cache": {
            "size": len(PLAYLIST_INFO_CACHE),
            "maxsize": PLAYLIST_INFO_CACHE.maxsize,
            "ttl_seconds": PLAYLIST_INFO_CACHE.ttl,
        },
    }


def fetch_video_info(video_id: str) -> VideoDetailResponse:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
    }
    with YoutubeDL(cast(Any, options)) as downloader:
        info = downloader.extract_info(video_url, download=False)

    formats = info.get("formats") or []
    selected_video_formats = _select_video_formats(formats)
    selected_m3u8_formats = _select_m3u8_formats(formats)
    selected_audio_format = _select_audio_format(formats)

    return VideoDetailResponse(
        id=info.get("id") or video_id,
        title=info.get("title") or "",
        duration=info.get("duration"),
        uploader=info.get("uploader"),
        channel_id=info.get("channel_id") or info.get("uploader_id"),
        video_formats=[_map_stream_info(fmt) for fmt in selected_video_formats],
        m3u8_formats=[_map_stream_info(fmt) for fmt in selected_m3u8_formats],
        audio_format=_map_stream_info(selected_audio_format) if selected_audio_format else None,
    )


def _select_video_formats(formats: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    indexed_by_id: dict[str, Mapping[str, Any]] = {}
    for fmt in formats:
        format_id = fmt.get("format_id")
        if not format_id:
            continue
        if fmt.get("ext") != "mp4":
            continue
        if fmt.get("url") in {None, ""}:
            continue
        indexed_by_id[format_id] = fmt

    selected: list[Mapping[str, Any]] = []
    for format_id in DESIRED_VIDEO_FORMAT_IDS:
        fmt = indexed_by_id.get(format_id)
        if fmt:
            selected.append(fmt)
    return selected


def _select_m3u8_formats(formats: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for fmt in formats:
        format_id = fmt.get("format_id")
        if not format_id or format_id not in DESIRED_M3U8_FORMAT_IDS:
            continue
        url = fmt.get("url")
        if not isinstance(url, str) or not url.endswith(".m3u8"):
            continue
        selected.append(fmt)
    return selected


def _select_audio_format(formats: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for fmt in formats:
        if fmt.get("format_id") != DESIRED_AUDIO_FORMAT_ID:
            continue
        if fmt.get("ext") != "m4a":
            continue
        if fmt.get("url") in {None, ""}:
            continue
        return fmt
    return None


def _map_stream_info(fmt: Mapping[str, Any]) -> StreamInfo:
    return StreamInfo(
        format_id=fmt.get("format_id", ""),
        ext=fmt.get("ext", ""),
        url=fmt.get("url", ""),
        width=fmt.get("width"),
        height=fmt.get("height"),
        fps=fmt.get("fps"),
        bitrate=fmt.get("tbr"),
        filesize=fmt.get("filesize"),
        filesize_approx=fmt.get("filesize_approx"),
    )


@cached(cache=VIDEO_INFO_CACHE, key=lambda video_id: video_id)
async def _fetch_video_info_cached(video_id: str) -> VideoDetailResponse:
    return await asyncio.to_thread(fetch_video_info, video_id)


async def fetch_video_info_cached(
    video_id: str, *, force_reload: bool = False
) -> VideoDetailResponse:
    if force_reload:
        VIDEO_INFO_CACHE.pop(video_id, None)
        return await asyncio.to_thread(fetch_video_info, video_id)

    result = await _fetch_video_info_cached(video_id)
    if not result.video_formats and result.audio_format is None:
        VIDEO_INFO_CACHE.pop(video_id, None)
    return result


def _coerce_optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _extract_playlist_info(playlist_id: str) -> Mapping[str, Any]:
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "extract_flat": True,
    }
    with YoutubeDL(cast(Any, options)) as downloader:
        return downloader.extract_info(playlist_url, download=False)


async def _build_playlist_response(playlist_id: str) -> PlaylistDetailResponse:
    info = await asyncio.to_thread(_extract_playlist_info, playlist_id)
    entries = info.get("entries") or []
    videos: list[PlaylistVideoSummary] = []
    seen_ids: set[str] = set()

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        entry_id = cast(str | None, entry.get("id") or entry.get("url"))
        if not entry_id or entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        videos.append(
            PlaylistVideoSummary(
                id=entry_id,
                title=cast(str, entry.get("title") or ""),
                duration=_coerce_optional_int(entry.get("duration")),
                uploader=cast(str | None, entry.get("uploader")),
                channel_id=cast(str | None, entry.get("channel_id") or entry.get("uploader_id")),
            )
        )

    return PlaylistDetailResponse(
        id=info.get("id") or playlist_id,
        title=cast(str | None, info.get("title")),
        uploader=cast(str | None, info.get("uploader")),
        channel_id=cast(str | None, info.get("channel_id") or info.get("uploader_id")),
        video_count=len(videos),
        videos=videos,
    )


@cached(cache=PLAYLIST_INFO_CACHE, key=lambda playlist_id: playlist_id)
async def _fetch_playlist_info_cached(playlist_id: str) -> PlaylistDetailResponse:
    return await _build_playlist_response(playlist_id)


async def fetch_playlist_info_cached(
    playlist_id: str, *, force_reload: bool = False
) -> PlaylistDetailResponse:
    if force_reload:
        PLAYLIST_INFO_CACHE.pop(playlist_id, None)
        return await _build_playlist_response(playlist_id)

    result = await _fetch_playlist_info_cached(playlist_id)
    if not result.videos:
        PLAYLIST_INFO_CACHE.pop(playlist_id, None)
    return result


@app.options("/m3u8_proxy", tags=["video"], name="proxy_m3u8_options")
async def proxy_m3u8_options() -> Response:
    response = Response(status_code=204)
    response.headers.update(_PROXY_CORS_HEADERS)
    return response


@app.get("/m3u8_proxy", summary="Proxy m3u8 playlists", tags=["video"], name="proxy_m3u8")
async def proxy_m3u8(url: str, request: Request) -> Response:
    if not url.lower().endswith(".m3u8"):
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'url' must end with .m3u8",
            headers=_PROXY_CORS_HEADERS.copy(),
        )

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'url' must be an absolute http(s) URL",
            headers=_PROXY_CORS_HEADERS.copy(),
        )

    try:
        async with httpx.AsyncClient() as client:
            upstream_response = await client.get(url)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve m3u8 content",
            headers=_PROXY_CORS_HEADERS.copy(),
        ) from exc

    if upstream_response.status_code >= 400:
        raise HTTPException(
            status_code=upstream_response.status_code,
            detail="Upstream server responded with an error",
            headers=_PROXY_CORS_HEADERS.copy(),
        )

    playlist_text = upstream_response.text
    proxy_segment_base = str(request.url_for("proxy_segment"))
    upstream_final_url = str(upstream_response.url)
    rewritten_lines: list[str] = []
    for original_line in playlist_text.splitlines():
        stripped = original_line.strip()
        if stripped and not stripped.startswith("#"):
            absolute_url = urljoin(upstream_final_url, stripped)
            proxied_segment = f"{proxy_segment_base}?url={quote(absolute_url, safe='')}"
            rewritten_lines.append(proxied_segment)
        else:
            rewritten_lines.append(original_line)
    rewritten_body = "\n".join(rewritten_lines)
    if playlist_text.endswith("\n"):
        rewritten_body += "\n"

    media_type = upstream_response.headers.get(
        "content-type", "application/vnd.apple.mpegurl"
    )
    response = Response(content=rewritten_body, media_type=media_type)
    response.headers.update(_PROXY_CORS_HEADERS)
    return response


@app.options("/seg_proxy", tags=["video"], name="proxy_segment_options")
async def proxy_segment_options() -> Response:
    response = Response(status_code=204)
    response.headers.update(_PROXY_CORS_HEADERS)
    return response


@app.get("/seg_proxy", summary="Proxy HLS segments", tags=["video"], name="proxy_segment")
async def proxy_segment(url: str) -> Response:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'url' must be an absolute http(s) URL",
            headers=_PROXY_CORS_HEADERS.copy(),
        )

    hostname = parsed.hostname or ""
    if not hostname.endswith("googlevideo.com"):
        raise HTTPException(
            status_code=400,
            detail="Segments may only be proxied from googlevideo.com",
            headers=_PROXY_CORS_HEADERS.copy(),
        )

    try:
        async with httpx.AsyncClient() as client:
            upstream_response = await client.get(url)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve segment content",
            headers=_PROXY_CORS_HEADERS.copy(),
        ) from exc

    if upstream_response.status_code >= 400:
        raise HTTPException(
            status_code=upstream_response.status_code,
            detail="Upstream server responded with an error",
            headers=_PROXY_CORS_HEADERS.copy(),
        )

    media_type = upstream_response.headers.get("content-type", "video/MP2T")
    response = Response(content=upstream_response.content, media_type=media_type)
    response.headers.update(_PROXY_CORS_HEADERS)
    return response


@app.get("/v1/video/{video_id}", summary="Retrieve video details", tags=["video"])
async def read_video(
    video_id: str,
    request: Request,
    force_reload: bool = False,
    _: None = Depends(enforce_api_key),
) -> VideoDetailResponse:
    try:
        base_response = await fetch_video_info_cached(video_id, force_reload=force_reload)
    except DownloadError as exc:
        raise HTTPException(status_code=404, detail="Video not found or unavailable") from exc
    except Exception as exc:  # pragma: no cover - unexpected failures
        raise HTTPException(status_code=500, detail="Failed to retrieve video information") from exc

    response = base_response.model_copy(deep=True)
    proxy_base_url = str(request.url_for("proxy_m3u8"))
    for stream in response.m3u8_formats:
        stream_url = stream.url
        if not stream_url:
            continue
        stream.proxied_url = f"{proxy_base_url}?url={quote(stream_url, safe='')}"

    return response


@app.get(
    "/v1/playlists/{playlist_id}",
    summary="Retrieve playlist video details",
    tags=["playlist"],
)
async def read_playlist(
    playlist_id: str, force_reload: bool = False, _: None = Depends(enforce_api_key)
) -> PlaylistDetailResponse:
    try:
        return await fetch_playlist_info_cached(playlist_id, force_reload=force_reload)
    except DownloadError as exc:
        raise HTTPException(status_code=404, detail="Playlist not found or unavailable") from exc
    except Exception as exc:  # pragma: no cover - unexpected failures
        raise HTTPException(
            status_code=500, detail="Failed to retrieve playlist information"
        ) from exc


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
