from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

app = FastAPI(title="yt-dlp API", version="0.1.0")

DESIRED_VIDEO_FORMAT_IDS: tuple[str, ...] = ("134", "135", "136", "137", "298", "299")
DESIRED_AUDIO_FORMAT_ID = "140"


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


class VideoDetailResponse(BaseModel):
    id: str
    title: str
    duration: int | None = None
    uploader: str | None = None
    video_formats: Sequence[StreamInfo] = ()
    audio_format: StreamInfo | None = None


@app.get("/health", summary="Health check", tags=["system"])
def read_health() -> Mapping[str, str]:
    return {"status": "ok"}


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
    selected_audio_format = _select_audio_format(formats)

    return VideoDetailResponse(
        id=info.get("id") or video_id,
        title=info.get("title") or "",
        duration=info.get("duration"),
        uploader=info.get("uploader"),
        video_formats=[_map_stream_info(fmt) for fmt in selected_video_formats],
        audio_format=_map_stream_info(selected_audio_format) if selected_audio_format else None,
    )


@app.get("/v1/video/{video_id}", summary="Retrieve video details", tags=["video"])
async def read_video(video_id: str) -> VideoDetailResponse:
    try:
        return await asyncio.to_thread(fetch_video_info, video_id)
    except DownloadError as exc:
        raise HTTPException(status_code=404, detail="Video not found or unavailable") from exc
    except Exception as exc:  # pragma: no cover - unexpected failures
        raise HTTPException(status_code=500, detail="Failed to retrieve video information") from exc


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
