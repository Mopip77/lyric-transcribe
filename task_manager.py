"""Task management with SSE support and refresh recovery."""

import asyncio
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from queue import Queue as ThreadQueue, Empty as QueueEmpty
from concurrent.futures import ThreadPoolExecutor

from models import (
    Config,
    TaskPhase,
    FileStatus,
    TaskProgress,
    TaskStatus,
)
from transcriber import transcribe_audio
from tagger import embed_lyric


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def format_duration(seconds: float) -> str:
    """Format duration as mm:ss."""
    if seconds <= 0:
        return ""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


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
    start_time: float = 0.0  # Unix timestamp when task started
    current_duration: str = ""  # Duration of current file being processed


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
        self.output_buffer: deque[dict] = deque(maxlen=2000)  # Increased for long audio
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._task_runner: asyncio.Task | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

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
        queue = asyncio.Queue(maxsize=2000)  # Increased for long audio
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
            duration=task.current_duration,
        )

        return TaskStatus(
            running=task.phase not in [TaskPhase.COMPLETED, TaskPhase.FAILED, TaskPhase.CANCELLED],
            progress=progress,
            recent_output=list(self.output_buffer),
            start_time=task.start_time if task.start_time > 0 else None,
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
        task.start_time = time.time()  # Record task start time
        loop = asyncio.get_running_loop()

        for i, file_task in enumerate(task.files):
            if task.cancelled:
                break

            task.current_index = i
            file_task.status = FileStatus.PROCESSING

            # Get audio duration
            duration = get_audio_duration(file_task.source_path)
            duration_str = format_duration(duration)
            task.current_duration = duration_str  # Store for status recovery

            await self.broadcast("progress", {
                "current": i + 1,
                "total": len(task.files),
                "phase": "transcribing",
                "file": file_task.name,
                "duration": duration_str,
            })

            try:
                # Check if LRC already exists
                lyric_exists = Path(file_task.lyric_path).exists()

                if not lyric_exists:
                    # Transcribe
                    task.phase = TaskPhase.TRANSCRIBING

                    # Use a thread-safe queue to collect transcribe lines
                    line_queue: ThreadQueue = ThreadQueue()
                    transcribe_done = False
                    transcribe_error = None

                    def on_transcribe_line(timestamp: str, text: str):
                        line_queue.put(("line", timestamp, text))

                    # Run transcription in thread pool
                    def do_transcribe():
                        nonlocal transcribe_done, transcribe_error
                        try:
                            transcribe_audio(
                                file_task.source_path,
                                file_task.lyric_path,
                                model=config.model,
                                language=config.language,
                                prompt=config.prompt,
                                callback=on_transcribe_line,
                            )
                            line_queue.put(("done", None, None))
                        except Exception as e:
                            line_queue.put(("error", str(e), None))

                    # Submit to executor
                    loop.run_in_executor(self._executor, do_transcribe)

                    # Process queue until done signal
                    finished = False
                    while not finished:
                        # Process all available items
                        while True:
                            try:
                                item = line_queue.get_nowait()
                            except QueueEmpty:
                                # No more items, wait a bit
                                await asyncio.sleep(0.1)
                                break

                            msg_type, arg1, arg2 = item

                            if msg_type == "line":
                                await self.broadcast("transcribe_line", {
                                    "time": arg1,
                                    "text": arg2,
                                })
                            elif msg_type == "done":
                                finished = True
                                break
                            elif msg_type == "error":
                                raise RuntimeError(arg1)

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
                        "duration": duration_str,
                    })

                    # Capture variables for closure
                    src = file_task.source_path
                    lrc = file_task.lyric_path
                    out = file_task.output_path
                    singer = config.singer_name
                    album = config.album_name
                    cover = config.cover_path

                    def do_embed():
                        return embed_lyric(src, lrc, out, singer, album, cover)

                    await loop.run_in_executor(None, do_embed)

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
