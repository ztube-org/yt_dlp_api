# yt-dlp-api

A FastAPI-based service prepared to expose functionality powered by `yt-dlp`.

## Getting Started

1. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install the project with runtime and development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Running the API Server

Launch the development server with auto-reload enabled:
```bash
uvicorn main:app --reload
```
The application exposes a basic health-check endpoint at `GET /health` that responds with `{"status": "ok"}`.

You can also start the server via the module entry point:
```bash
python -m main
```

## Tooling

- `ruff`: Formats code and enforces lint rules. Run `ruff check .` to lint and `ruff format .` to apply formatting.
- `basedpyright`: Provides static type checking. Run `basedpyright` from the project root to validate types.

## Next Steps

With the skeleton in place, you can expand the API by adding routes that leverage `yt-dlp` to retrieve or process media metadata as needed.
