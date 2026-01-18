# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lyric Transcribe is a FastAPI-based web application that transcribes audio files to synchronized lyrics (LRC format) using Whisper, then embeds those lyrics into MP3 files with ID3 tags. The application features real-time progress streaming via Server-Sent Events (SSE) for live transcription updates.

## Commands

### Running the application
```bash
python app.py
# or
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Running tests
```bash
# Test transcription streaming and event management
python test_streaming.py

# Test SSE client connection (requires server running)
python test_sse_client.py
```

### Installing dependencies
```bash
pip install -r requirements.txt
```

## Architecture

### Core Components

**FastAPI Application (app.py)**
- Serves static frontend at `/static/index.html`
- REST API endpoints for config, files, models, and task management
- SSE endpoint at `/api/task/stream` for real-time progress updates
- Loads/persists configuration from `config.json`

**Task Manager (task_manager.py)**
- Singleton pattern managing task execution and event broadcasting
- Processes files through two phases: transcribing → embedding
- Uses ThreadPoolExecutor for blocking operations (transcription, embedding)
- Maintains deque buffer (maxlen=2000) for SSE event replay on reconnection
- SSE subscriber pattern with asyncio.Queue for each connected client
- Skips files if LRC or MP3 output already exists

**Transcriber (transcriber.py)**
- Wraps pywhispercpp for audio transcription
- Converts audio to WAV format via ffmpeg before processing
- Real-time callback system via `new_segment_callback` for streaming updates
- Outputs LRC format with timestamps `[mm:ss.xx]`

**Tagger (tagger.py)**
- Embeds lyrics and metadata into MP3 files using mutagen
- Converts non-MP3 files to MP3 via ffmpeg
- Adds ID3v2 tags: title, artist (singer), album, cover art (APIC), synchronized lyrics (SYLT)
- SYLT format uses milliseconds with language code "zho"

### Data Flow

1. User selects audio files and starts task via `/api/task/start`
2. TaskManager creates FileTask objects and spawns async task runner
3. For each file:
   - Check if LRC exists, skip transcription if present
   - Transcribe audio → callback streams lines → broadcast `transcribe_line` events
   - Check if MP3 exists, skip embedding if present
   - Embed lyrics into MP3 with ID3 tags
4. SSE clients receive real-time events: `progress`, `transcribe_line`, `file_complete`, `task_complete`
5. On browser refresh, `/api/task/status` returns buffered events for recovery

### Event Types (SSE)

- `progress`: Task progress with phase (transcribing/embedding), file, duration
- `transcribe_line`: Individual lyric line with timestamp
- `transcribe_complete`: Transcription finished for a file
- `file_complete`: File processing done (success/failure)
- `task_complete`: All files processed
- `task_cancelled`: Task was cancelled
- `error`: Processing error occurred

### Configuration (config.json)

- `source_dir`: Input audio files directory (supports .m4a, .mp3, .mp4, .wav, .flac, .ogg, .aac)
- `lyric_dir`: Output directory for .lrc files
- `output_dir`: Output directory for tagged .mp3 files
- `model`: Whisper model (default: "large-v3-turbo")
- `language`: Transcription language code (default: "zh")
- `prompt`: Initial prompt for better transcription accuracy
- `singer_name`, `album_name`, `cover_path`: ID3 tag metadata

## Key Implementation Details

### Threading and Async

- Main FastAPI app runs on asyncio event loop
- Blocking operations (transcribe, embed) run in ThreadPoolExecutor
- Thread-safe Queue bridges sync callbacks to async event loop
- SSE uses asyncio.Queue for each subscriber

### Real-time Streaming

- Transcriber uses `new_segment_callback` for segment-level updates
- Callback puts items in thread-safe Queue
- Async loop polls queue and broadcasts to SSE subscribers
- 30-second keepalive in SSE prevents connection timeout

### Buffer and Recovery

- output_buffer (deque, maxlen=2000) stores all events
- `/api/task/status` returns recent_output for browser refresh recovery
- Each SSE queue has maxsize=2000 to match buffer capacity

### File Processing Logic

- Files are skipped intelligently: if LRC exists, skip transcription; if MP3 exists, skip embedding
- This enables resuming interrupted batches without reprocessing

## Dependencies

- **fastapi**: Web framework
- **uvicorn**: ASGI server
- **pywhispercpp**: Whisper.cpp Python bindings for transcription
- **mutagen**: ID3 tag manipulation for MP3 files
- **pydantic**: Data validation and models
- **ffmpeg** (system): Audio format conversion (WAV/MP3)
- **ffprobe** (system): Audio duration extraction
