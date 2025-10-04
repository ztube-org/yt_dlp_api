from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Ensure the application package is importable when running tests directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Any]]:
    """Reload the app module with a test API key and mocked integrations."""

    monkeypatch.setenv("YT_DLP_API_KEY", "test-key")
    main_module = importlib.import_module("yt_dlp_api.main")
    module = importlib.reload(main_module)

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[explicit-any]
        return func(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", fake_to_thread)

    def fake_fetch_video_info(video_id: str) -> Any:
        return module.VideoDetailResponse(
            id=video_id,
            title=f"Video-{video_id}",
            duration=123,
            uploader="Uploader",
            channel_id="channel-123",
            video_formats=[
                module.StreamInfo(
                    format_id="136",
                    ext="mp4",
                    url=f"https://cdn.example.com/video/{video_id}",
                )
            ],
            audio_format=module.StreamInfo(
                format_id="140",
                ext="m4a",
                url=f"https://cdn.example.com/audio/{video_id}",
            ),
        )

    monkeypatch.setattr(module, "fetch_video_info", fake_fetch_video_info)

    def fake_extract_playlist_info(playlist_id: str) -> dict[str, Any]:
        return {
            "id": playlist_id,
            "title": "Playlist Title",
            "uploader": "Playlist Uploader",
            "channel_id": "playlist-channel",
            "entries": [
                {
                    "id": "video1",
                    "title": "First Video",
                    "duration": 60,
                    "uploader": "Uploader1",
                    "channel_id": "channel1",
                },
                {
                    "url": "video2",
                    "title": "Second Video",
                    "duration": "120",
                    "uploader": "Uploader2",
                    "uploader_id": "channel2",
                },
                {
                    "id": "video1",
                    "title": "Duplicate Video",
                },
            ],
        }

    monkeypatch.setattr(module, "_extract_playlist_info", fake_extract_playlist_info)

    client = TestClient(module.app)
    yield client, module

    module.VIDEO_INFO_CACHE.clear()
    module.PLAYLIST_INFO_CACHE.clear()


def test_health_endpoint_reports_cache_stats(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["video_cache"]["size"] == 0
    assert payload["video_cache"]["maxsize"] == 1024
    assert payload["playlist_cache"]["size"] == 0


def test_video_endpoint_requires_authorization(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    response = client.get("/v1/video/abc123")
    assert response.status_code == 401


def test_video_endpoint_returns_payload(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    response = client.get(
        "/v1/video/abc123",
        headers={"Authorization": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "abc123"
    assert payload["title"] == "Video-abc123"
    assert payload["video_formats"][0]["format_id"] == "136"
    assert payload["audio_format"]["format_id"] == "140"


def test_force_reload_bypasses_video_cache(api: tuple[TestClient, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    client, module = api
    headers = {"Authorization": "test-key"}

    response = client.get("/v1/video/abc123", headers=headers)
    assert response.status_code == 200
    first_title = response.json()["title"]

    def alternate_fetch(video_id: str) -> Any:
        return module.VideoDetailResponse(
            id=video_id,
            title="Fresh Title",
            duration=321,
            uploader="New Uploader",
            channel_id="new-channel",
            video_formats=[],
            audio_format=None,
        )

    monkeypatch.setattr(module, "fetch_video_info", alternate_fetch)

    response = client.get("/v1/video/abc123?force_reload=true", headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Fresh Title"
    assert response.json()["title"] != first_title


def test_playlist_endpoint_returns_summary(api: tuple[TestClient, Any]) -> None:
    client, _ = api
    response = client.get(
        "/v1/playlists/demo-playlist",
        headers={"Authorization": "test-key"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "demo-playlist"
    assert payload["video_count"] == 2  # duplicates are removed
    assert {video["id"] for video in payload["videos"]} == {"video1", "video2"}
    assert payload["videos"][1]["duration"] == 120
