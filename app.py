"""FastAPI application for Lyric Transcribe."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from models import (
    Config,
    FileInfo,
    FileStatus,
    TaskStartRequest,
    TaskStatus,
)
from task_manager import task_manager, FileTask
from transcriber import get_available_models

app = FastAPI(title="Lyric Transcribe")

# Config file path
CONFIG_PATH = Path(__file__).parent / "config.json"

# Supported audio extensions
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".aac"}


def load_config() -> Config:
    """Load configuration from file."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Config(**data)
        except Exception:
            pass
    return Config()


def save_config(config: Config):
    """Save configuration to file."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)


# Mount static files
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
async def root():
    """Redirect to static index.html."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/api/config")
async def get_config() -> Config:
    """Get current configuration."""
    return load_config()


@app.post("/api/config")
async def update_config(config: Config) -> Config:
    """Update and persist configuration."""
    save_config(config)
    return config


@app.get("/api/models")
async def get_models() -> list[str]:
    """Get available whisper models."""
    return get_available_models()


@app.get("/api/paths/search")
async def search_paths(prefix: str = "", path_type: str = "directory") -> list[str]:
    """
    Search for paths matching the given prefix.
    
    Args:
        prefix: Path prefix to search for (e.g., "/Us" or "/Users/mcpp/Mus")
        path_type: Either "directory" or "file" (default: directory)
    
    Returns:
        List of matching absolute paths (max 20 results)
    """
    import os
    from pathlib import Path
    
    results = []
    max_results = 20
    
    # Handle empty prefix - return common directories
    if not prefix or prefix == "/":
        common_dirs = [
            Path.home(),
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
            Path.home() / "Music",
            Path.home() / "Pictures",
            Path.home() / "Videos",
        ]
        results = [str(d) for d in common_dirs if d.exists() and d.is_dir()]
        return results[:max_results]
    
    try:
        prefix_path = Path(prefix).expanduser()
        
        # If the prefix is an exact directory, return its contents
        if prefix_path.exists() and prefix_path.is_dir():
            try:
                for item in sorted(prefix_path.iterdir()):
                    if path_type == "directory" and not item.is_dir():
                        continue
                    if path_type == "file" and not item.is_file():
                        continue
                    results.append(str(item))
                    if len(results) >= max_results:
                        break
            except PermissionError:
                pass
        else:
            # Search for directories matching the prefix
            parent = prefix_path.parent
            name_prefix = prefix_path.name
            
            if parent.exists() and parent.is_dir():
                try:
                    for item in sorted(parent.iterdir()):
                        if not item.name.startswith(name_prefix):
                            continue
                        if path_type == "directory" and not item.is_dir():
                            continue
                        if path_type == "file" and not item.is_file():
                            continue
                        results.append(str(item))
                        if len(results) >= max_results:
                            break
                except PermissionError:
                    pass
    except Exception:
        # Return empty list on any error
        pass
    
    return results


@app.get("/api/files")
async def get_files() -> list[FileInfo]:
    """Get list of files to process."""
    config = load_config()

    if not config.source_dir:
        return []

    source_dir = Path(config.source_dir)
    if not source_dir.exists():
        return []

    lyric_dir = Path(config.lyric_dir) if config.lyric_dir else None
    output_dir = Path(config.output_dir) if config.output_dir else None

    files = []
    for file_path in sorted(source_dir.iterdir()):
        if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        stem = file_path.stem

        # Check if LRC exists
        has_lyric = False
        if lyric_dir:
            lrc_path = lyric_dir / f"{stem}.lrc"
            has_lyric = lrc_path.exists()

        # Check if output MP3 exists
        has_output = False
        if output_dir:
            output_path = output_dir / f"{stem}.mp3"
            has_output = output_path.exists()

        files.append(FileInfo(
            name=file_path.name,
            has_lyric=has_lyric,
            has_output=has_output,
            status=FileStatus.COMPLETED if (has_lyric and has_output) else FileStatus.PENDING,
        ))

    return files


@app.post("/api/task/start")
async def start_task(request: TaskStartRequest) -> dict:
    """Start processing task."""
    config = load_config()

    if not config.source_dir:
        raise HTTPException(status_code=400, detail="Source directory not configured")
    if not config.lyric_dir:
        raise HTTPException(status_code=400, detail="Lyric directory not configured")
    if not config.output_dir:
        raise HTTPException(status_code=400, detail="Output directory not configured")

    source_dir = Path(config.source_dir)
    lyric_dir = Path(config.lyric_dir)
    output_dir = Path(config.output_dir)

    # Build file tasks
    file_tasks = []
    for filename in request.files:
        source_path = source_dir / filename
        if not source_path.exists():
            continue

        stem = source_path.stem
        file_tasks.append(FileTask(
            name=filename,
            source_path=str(source_path),
            lyric_path=str(lyric_dir / f"{stem}.lrc"),
            output_path=str(output_dir / f"{stem}.mp3"),
        ))

    if not file_tasks:
        raise HTTPException(status_code=400, detail="No valid files to process")

    success = await task_manager.start_task(file_tasks, config)
    if not success:
        raise HTTPException(status_code=409, detail="Task already running")

    return {"success": True, "files_count": len(file_tasks)}


@app.get("/api/task/status")
async def get_task_status() -> TaskStatus:
    """Get current task status."""
    return task_manager.get_status()


@app.post("/api/task/cancel")
async def cancel_task() -> dict:
    """Cancel current task."""
    success = await task_manager.cancel_task()
    return {"success": success}


@app.get("/api/task/stream")
async def task_stream():
    """SSE endpoint for real-time progress."""
    async def event_generator():
        queue = task_manager.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

                    # Stop streaming if task is complete
                    if event['type'] in ['task_complete', 'task_cancelled']:
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        finally:
            task_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
