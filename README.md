# yt-dlp-api

A FastAPI-based service prepared to expose functionality powered by `yt-dlp`.

## Running the API Server

Launch the development server with auto-reload enabled:
```bash
uv run fastapi dev main.py
```

## Tooling

- `ruff`: Formats code and enforces lint rules. Run `ruff check .` to lint and `ruff format .` to apply formatting.
- `basedpyright`: Provides static type checking. Run `basedpyright` from the project root to validate types.

## Next Steps

With the skeleton in place, you can expand the API by adding routes that leverage `yt-dlp` to retrieve or process media metadata as needed.
