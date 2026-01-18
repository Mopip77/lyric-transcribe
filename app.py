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
from audio_merger import AudioMerger

app = FastAPI(title="Lyric Transcribe")

# Config file path
CONFIG_PATH = Path(__file__).parent / "config.json"

# Supported audio extensions
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".aac"}

# Audio merger instance
audio_merger = AudioMerger()
merge_progress_queue = None


# Merge request model
class MergeRequest(BaseModel):
    """Request model for audio merge."""
    files: list[str]
    output_name: str
    delete_sources: bool = False
    overwrite: bool = False


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

        # Get file size
        try:
            size_bytes = file_path.stat().st_size
        except Exception:
            size_bytes = 0

        files.append(FileInfo(
            name=file_path.name,
            has_lyric=has_lyric,
            has_output=has_output,
            status=FileStatus.COMPLETED if (has_lyric and has_output) else FileStatus.PENDING,
            size_bytes=size_bytes,
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


@app.get("/api/audio/check-exists")
async def check_file_exists(filename: str) -> dict:
    """Check if a file exists in the merge output directory."""
    config = load_config()
    
    if not config.merge_output_dir:
        return {"exists": False}
    
    output_path = Path(config.merge_output_dir) / filename
    return {"exists": output_path.exists()}


@app.post("/api/audio/merge")
async def merge_audio(request: MergeRequest) -> dict:
    """Start audio merge task."""
    config = load_config()

    if not config.merge_source_dir:
        raise HTTPException(status_code=400, detail="Merge source directory not configured")
    if not config.merge_output_dir:
        raise HTTPException(status_code=400, detail="Merge output directory not configured")

    source_dir = Path(config.merge_source_dir)
    output_dir = Path(config.merge_output_dir)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build source file paths
    source_files = []
    for filename in request.files:
        source_path = source_dir / filename
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        source_files.append(source_path)

    if len(source_files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 files required for merging")

    # Ensure WAV extension
    output_name = request.output_name
    if not output_name.endswith('.wav'):
        output_name = f"{output_name}.wav"

    output_path = output_dir / output_name

    # Check if file exists and not overwrite
    if output_path.exists() and not request.overwrite:
        raise HTTPException(status_code=409, detail=f"File already exists: {output_name}")

    # Start merge in background
    global merge_progress_queue
    merge_progress_queue = asyncio.Queue()

    async def run_merge():
        """Run merge operation."""
        try:
            # Send start event
            await merge_progress_queue.put({
                'type': 'merge_start',
                'data': {'file_count': len(source_files)}
            })

            # Progress callback
            async def progress_callback(progress_data):
                await merge_progress_queue.put({
                    'type': 'merge_progress',
                    'data': progress_data
                })

            # Run merge
            success = await audio_merger.merge_audio_files(
                source_files,
                output_path,
                progress_callback=lambda data: asyncio.create_task(progress_callback(data))
            )

            if success:
                # Delete source files if requested
                if request.delete_sources:
                    await audio_merger.delete_source_files(source_files)

                await merge_progress_queue.put({
                    'type': 'merge_complete',
                    'data': {'output_file': output_name}
                })
            else:
                await merge_progress_queue.put({
                    'type': 'merge_error',
                    'data': {'message': 'Merge failed'}
                })

        except Exception as e:
            await merge_progress_queue.put({
                'type': 'merge_error',
                'data': {'message': str(e)}
            })

    # Start merge task
    asyncio.create_task(run_merge())

    return {"success": True, "message": "Merge started"}


@app.get("/api/audio/merge/stream")
async def merge_stream():
    """SSE endpoint for merge progress."""
    async def event_generator():
        global merge_progress_queue
        
        if merge_progress_queue is None:
            merge_progress_queue = asyncio.Queue()
        
        try:
            while True:
                try:
                    event = await asyncio.wait_for(merge_progress_queue.get(), timeout=30.0)
                    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

                    # Stop streaming if merge is complete
                    if event['type'] in ['merge_complete', 'merge_error']:
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except Exception as e:
            print(f"Stream error: {e}")

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
