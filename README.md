# yt-dlp-api

A FastAPI-based service that surfaces selected `yt-dlp` capabilities over HTTP.

## Running the API Server

This project uses [pyprojectx](https://github.com/pyprojectx/pyprojectx) for repeatable developer workflows. After installing pyprojectx (`pip install pyprojectx`), use the bundled aliases:

```bash
px dev      # fastapi dev server with auto-reload
px test     # run pytest suite
px format   # apply ruff formatting
px lint     # run ruff lint checks
px typecheck  # run basedpyright static analysis
```

The `px dev` command launches the API at `http://127.0.0.1:8000` by default. You can still invoke the underlying commands directly if preferred:

```bash
uv run fastapi dev src/yt_dlp_api/main.py
```

## Authentication

Set `YT_DLP_API_KEY` to require clients to present an API key; omit it to keep the API open locally.

```bash
export YT_DLP_API_KEY="super-secret-key"
```

Clients must send the key in the `Authorization` header exactly as provided for protected endpoints (e.g., video and playlist routes).

```bash
curl -H "Authorization: super-secret-key" \
  "http://127.0.0.1:8000/v1/video/dQw4w9WgXcQ"
```

## API Overview

All endpoints support an optional `force_reload` query parameter (default `false`). When `true`, cached data for the requested resource is bypassed and re-fetched from YouTube.

### `GET /health`

- **Tags:** `system`
- **Description:** Returns service status plus cache statistics. This endpoint never requires an API key.

Example:
```bash
curl http://127.0.0.1:8000/health
```

Sample response body:
```json
{
  "status": "ok",
  "video_cache": {"size": 12, "maxsize": 1024, "ttl_seconds": 3600},
  "playlist_cache": {"size": 3, "maxsize": 256, "ttl_seconds": 1800}
}
```

### `GET /v1/video/{video_id}`

- **Tags:** `video`
- **Description:** Retrieves metadata for a single video—including selected MP4 stream variants and the preferred M4A audio stream.
- **Path Parameters:**
  - `video_id` – YouTube video identifier (e.g., `dQw4w9WgXcQ`).
- **Query Parameters:**
  - `force_reload` (`bool`, default `false`).

Sample request:
```bash
curl -H "Authorization: super-secret-key" \
  "http://127.0.0.1:8000/v1/video/dQw4w9WgXcQ?force_reload=true"
```

Sample response body:
```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Example Video",
  "duration": 212,
  "uploader": "Example Channel",
  "channel_id": "UCxxxx",
  "video_formats": [
    {"format_id": "136", "ext": "mp4", "url": "…"}
  ],
  "audio_format": {"format_id": "140", "ext": "m4a", "url": "…"}
}
```

### `GET /v1/playlists/{playlist_id}`

- **Tags:** `playlist`
- **Description:** Returns playlist metadata plus a fast, flattened list of videos (no stream URLs).
- **Path Parameters:**
  - `playlist_id` – YouTube playlist identifier (e.g., `PLvMVu6E_UeEuDrqjc1EN31WSVe18NnVC3`).
- **Query Parameters:**
  - `force_reload` (`bool`, default `false`).

Sample request:
```bash
curl -H "Authorization: super-secret-key" \
  "http://127.0.0.1:8000/v1/playlists/PLvMVu6E_UeEuDrqjc1EN31WSVe18NnVC3"
```

Example response snippet:
```json
{
  "id": "PLvMVu6E_UeEuDrqjc1EN31WSVe18NnVC3",
  "title": "Example Playlist",
  "uploader": "Example Channel",
  "channel_id": "UCyyyy",
  "video_count": 42,
  "videos": [
    {"id": "dQw4w9WgXcQ", "title": "Example Video", "duration": 212}
  ]
}
```

## Tooling

- `ruff`: Formats code and enforces lint rules. Run `ruff check .` to lint and `ruff format .` to apply formatting.
- `basedpyright`: Provides static type checking. Run `basedpyright` from the project root to validate types.
