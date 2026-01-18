"""Pydantic data models for Lyric Transcribe."""

from enum import Enum
from pydantic import BaseModel


class TaskPhase(str, Enum):
    """Task processing phase."""
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FileStatus(str, Enum):
    """File processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Config(BaseModel):
    """Application configuration."""
    # Directory configuration
    source_dir: str = ""
    lyric_dir: str = ""
    output_dir: str = ""

    # Merge configuration
    merge_source_dir: str = ""
    merge_output_dir: str = ""

    # Transcription configuration
    model: str = "large-v3-turbo"
    language: str = "zh"
    prompt: str = "歌词 简体中文"

    # ID3 tag configuration
    singer_name: str = ""
    album_name: str = ""
    cover_path: str = ""


class FileInfo(BaseModel):
    """Information about a source file."""
    name: str
    has_lyric: bool
    has_output: bool
    status: FileStatus = FileStatus.PENDING
    size_bytes: int = 0  # File size in bytes


class TaskStartRequest(BaseModel):
    """Request to start a processing task."""
    files: list[str]


class TaskProgress(BaseModel):
    """Task progress information."""
    current: int
    total: int
    phase: TaskPhase
    file: str
    duration: str = ""


class TranscribeLine(BaseModel):
    """A transcribed lyric line."""
    time: str
    text: str


class FileComplete(BaseModel):
    """File completion event."""
    file: str
    success: bool
    message: str = ""


class TaskComplete(BaseModel):
    """Task completion event."""
    success_count: int
    fail_count: int


class TaskStatus(BaseModel):
    """Current task status for refresh recovery."""
    running: bool
    progress: TaskProgress | None = None
    recent_output: list[dict] = []
    start_time: float | None = None  # Unix timestamp when task started


class ErrorEvent(BaseModel):
    """Error event."""
    file: str
    message: str
