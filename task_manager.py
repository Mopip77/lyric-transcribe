"""Task management with SSE support and refresh recovery."""

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

from models import (
    Config,
    TaskPhase,
    FileStatus,
    TaskProgress,
    TaskStatus,
)
from transcriber import transcribe_audio
from tagger import embed_lyric


@dataclass
class FileTask:
    """Individual file task."""
    name: str
    source_path: str
    lyric_path: str
    output_path: str
    status: FileStatus = FileStatus.PENDING
    error_message: str = ""


@dataclass
class Task:
    """Processing task containing multiple files."""
    files: list[FileTask]
    current_index: int = 0
    phase: TaskPhase = TaskPhase.PENDING
    cancelled: bool = False
    success_count: int = 0
    fail_count: int = 0


class TaskManager:
    """Singleton task manager with SSE broadcasting."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.current_task: Task | None = None
        self.output_buffer: deque[dict] = deque(maxlen=100)
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._task_runner: asyncio.Task | None = None

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast event to all SSE subscribers."""
        event = {"type": event_type, "data": data, "timestamp": time.time()}
        self.output_buffer.append(event)

        # Send to all subscribers
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        # Remove dead subscribers
        for queue in dead_queues:
            self._subscribers.remove(queue)

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to SSE events."""
        queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from SSE events."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def get_status(self) -> TaskStatus:
        """Get current task status for refresh recovery."""
        if self.current_task is None:
            return TaskStatus(running=False)

        task = self.current_task
        progress = TaskProgress(
            current=task.current_index + 1,
            total=len(task.files),
            phase=task.phase,
            file=task.files[task.current_index].name if task.files else "",
        )

        return TaskStatus(
            running=task.phase not in [TaskPhase.COMPLETED, TaskPhase.FAILED, TaskPhase.CANCELLED],
            progress=progress,
            recent_output=list(self.output_buffer),
        )

    async def start_task(self, files: list[FileTask], config: Config) -> bool:
        """Start a new processing task."""
        async with self._lock:
            if self.current_task and self.current_task.phase not in [
                TaskPhase.COMPLETED, TaskPhase.FAILED, TaskPhase.CANCELLED
            ]:
                return False

            self.current_task = Task(files=files)
            self.output_buffer.clear()

        # Start processing in background
        self._task_runner = asyncio.create_task(self._run_task(config))
        return True

    async def cancel_task(self) -> bool:
        """Cancel the current task."""
        if self.current_task is None:
            return False

        self.current_task.cancelled = True
        self.current_task.phase = TaskPhase.CANCELLED

        await self.broadcast("task_cancelled", {})
        return True

    async def _run_task(self, config: Config):
        """Run the processing task."""
        task = self.current_task
        if task is None:
            return

        task.phase = TaskPhase.PENDING

        for i, file_task in enumerate(task.files):
            if task.cancelled:
                break

            task.current_index = i
            file_task.status = FileStatus.PROCESSING

            await self.broadcast("progress", {
                "current": i + 1,
                "total": len(task.files),
                "phase": "transcribing",
                "file": file_task.name,
            })

            try:
                # Check if LRC already exists
                lyric_exists = Path(file_task.lyric_path).exists()

                if not lyric_exists:
                    # Transcribe
                    task.phase = TaskPhase.TRANSCRIBING

                    def on_transcribe_line(timestamp: str, text: str):
                        # Queue the broadcast for async execution
                        asyncio.get_event_loop().call_soon_threadsafe(
                            lambda: asyncio.create_task(
                                self.broadcast("transcribe_line", {
                                    "time": timestamp,
                                    "text": text,
                                })
                            )
                        )

                    # Run transcription in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: transcribe_audio(
                            file_task.source_path,
                            file_task.lyric_path,
                            model=config.model,
                            language=config.language,
                            prompt=config.prompt,
                            callback=on_transcribe_line,
                        )
                    )

                    await self.broadcast("transcribe_complete", {
                        "file": file_task.name,
                    })

                # Check if output already exists
                output_exists = Path(file_task.output_path).exists()

                if not output_exists:
                    # Embed lyrics
                    task.phase = TaskPhase.EMBEDDING

                    await self.broadcast("progress", {
                        "current": i + 1,
                        "total": len(task.files),
                        "phase": "embedding",
                        "file": file_task.name,
                    })

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: embed_lyric(
                            file_task.source_path,
                            file_task.lyric_path,
                            file_task.output_path,
                            singer=config.singer_name,
                            album=config.album_name,
                            cover_path=config.cover_path,
                        )
                    )

                file_task.status = FileStatus.COMPLETED
                task.success_count += 1

                await self.broadcast("file_complete", {
                    "file": file_task.name,
                    "success": True,
                    "message": "",
                })

            except Exception as e:
                file_task.status = FileStatus.FAILED
                file_task.error_message = str(e)
                task.fail_count += 1

                await self.broadcast("error", {
                    "file": file_task.name,
                    "message": str(e),
                })

                await self.broadcast("file_complete", {
                    "file": file_task.name,
                    "success": False,
                    "message": str(e),
                })

        # Task complete
        if task.cancelled:
            task.phase = TaskPhase.CANCELLED
        else:
            task.phase = TaskPhase.COMPLETED

        await self.broadcast("task_complete", {
            "success_count": task.success_count,
            "fail_count": task.fail_count,
        })


# Global singleton
task_manager = TaskManager()
