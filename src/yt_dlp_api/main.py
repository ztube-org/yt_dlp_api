from collections.abc import Mapping

from fastapi import FastAPI

app = FastAPI(title="yt-dlp API", version="0.1.0")


@app.get("/health", summary="Health check", tags=["system"])
def read_health() -> Mapping[str, str]:
    return {"status": "ok"}


@app.get("/v1/video/{video_id}", summary="Retrieve video details", tags=["video"])
def read_video(video_id: str) -> Mapping[str, str]:
    raise NotImplementedError


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
