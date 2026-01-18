#!/usr/bin/env python
"""Test script to verify transcription streaming and complete output."""

import asyncio
import sys
import tempfile
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from transcriber import transcribe_audio


def test_transcriber_callback():
    """Test that transcriber callback is called in real-time."""
    print("=" * 60)
    print("Test 1: Transcriber callback test")
    print("=" * 60)

    # Create a short test audio file using ffmpeg (sine wave)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_audio = Path(tmpdir) / "test.wav"
        test_lrc = Path(tmpdir) / "test.lrc"

        # Generate 5 seconds of audio with speech-like noise
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=5",
            "-ar", "16000",
            "-ac", "1",
            str(test_audio)
        ], capture_output=True, check=True)

        print(f"Created test audio: {test_audio}")

        callback_times = []

        def on_line(timestamp: str, text: str):
            import time
            callback_times.append(time.time())
            print(f"  [CALLBACK] {timestamp} {text}")

        print("Starting transcription...")
        start_time = __import__("time").time()

        try:
            transcribe_audio(
                str(test_audio),
                str(test_lrc),
                model="tiny",  # Use tiny model for fast testing
                language="en",
                prompt="",
                callback=on_line,
            )
        except Exception as e:
            print(f"  Transcription error (expected for sine wave): {e}")

        end_time = __import__("time").time()
        print(f"Transcription took: {end_time - start_time:.2f}s")
        print(f"Callback was called {len(callback_times)} times")

        if test_lrc.exists():
            content = test_lrc.read_text()
            print(f"LRC file content ({len(content.splitlines())} lines):")
            for line in content.splitlines()[:5]:
                print(f"  {line}")
            if len(content.splitlines()) > 5:
                print(f"  ... and {len(content.splitlines()) - 5} more lines")


async def test_task_manager_streaming():
    """Test that task manager properly streams events."""
    print("\n" + "=" * 60)
    print("Test 2: Task manager streaming test")
    print("=" * 60)

    from task_manager import TaskManager, FileTask
    from models import Config

    # Create a fresh task manager instance for testing
    TaskManager._instance = None
    TaskManager._instance = None  # Reset singleton
    manager = TaskManager()
    manager._initialized = False
    manager.__init__()

    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "source"
        lyric_dir = Path(tmpdir) / "lyric"
        output_dir = Path(tmpdir) / "output"
        source_dir.mkdir()
        lyric_dir.mkdir()
        output_dir.mkdir()

        # Create test audio
        test_audio = source_dir / "test.wav"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=3",
            "-ar", "16000",
            "-ac", "1",
            str(test_audio)
        ], capture_output=True, check=True)

        config = Config(
            source_dir=str(source_dir),
            lyric_dir=str(lyric_dir),
            output_dir=str(output_dir),
            model="tiny",
            language="en",
            prompt="",
        )

        file_tasks = [
            FileTask(
                name="test.wav",
                source_path=str(test_audio),
                lyric_path=str(lyric_dir / "test.lrc"),
                output_path=str(output_dir / "test.mp3"),
            )
        ]

        # Subscribe to events
        queue = manager.subscribe()
        events_received = []

        async def collect_events():
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                    events_received.append(event)
                    print(f"  [EVENT] {event['type']}: {event['data']}")
                    if event['type'] in ['task_complete', 'task_cancelled']:
                        break
                except asyncio.TimeoutError:
                    print("  [TIMEOUT] No events received for 60s")
                    break

        # Start task and collect events
        print("Starting task...")
        collector = asyncio.create_task(collect_events())
        await manager.start_task(file_tasks, config)
        await collector

        print(f"\nTotal events received: {len(events_received)}")

        # Check event types
        event_types = [e['type'] for e in events_received]
        print(f"Event types: {set(event_types)}")

        # Count transcribe_line events
        line_events = [e for e in events_received if e['type'] == 'transcribe_line']
        print(f"Transcribe line events: {len(line_events)}")

        # Verify task completed
        if 'task_complete' in event_types:
            complete_event = [e for e in events_received if e['type'] == 'task_complete'][0]
            print(f"Task complete: success={complete_event['data']['success_count']}, fail={complete_event['data']['fail_count']}")
        else:
            print("WARNING: task_complete event not received!")

        # Check for file_complete event
        if 'file_complete' in event_types:
            print("file_complete event received: OK")
        else:
            print("WARNING: file_complete event not received!")

        # Check output files
        lrc_file = lyric_dir / "test.lrc"
        mp3_file = output_dir / "test.mp3"
        print(f"\nOutput files:")
        print(f"  LRC exists: {lrc_file.exists()}")
        print(f"  MP3 exists: {mp3_file.exists()}")

        if lrc_file.exists():
            lrc_lines = lrc_file.read_text().splitlines()
            print(f"  LRC lines: {len(lrc_lines)}")


async def test_many_events():
    """Test that many events can be processed without data loss."""
    print("\n" + "=" * 60)
    print("Test 3: Many events stress test")
    print("=" * 60)

    from task_manager import TaskManager

    # Create fresh instance
    TaskManager._instance = None
    manager = TaskManager()

    # Subscribe
    queue = manager.subscribe()

    # Broadcast many events
    num_events = 500
    print(f"Broadcasting {num_events} events...")

    for i in range(num_events):
        await manager.broadcast("transcribe_line", {
            "time": f"[{i // 60:02d}:{i % 60:02d}.00]",
            "text": f"Test line {i}",
        })

    # Collect all events
    received = 0
    while not queue.empty():
        await queue.get()
        received += 1

    print(f"Events sent: {num_events}")
    print(f"Events received: {received}")
    print(f"Buffer size: {len(manager.output_buffer)}")

    if received == num_events:
        print("SUCCESS: All events received!")
    else:
        print(f"WARNING: Lost {num_events - received} events")

    # Verify buffer contains events for refresh recovery
    assert len(manager.output_buffer) <= 2000, "Buffer should respect maxlen"
    print(f"Buffer maxlen respected: {len(manager.output_buffer)} <= 2000")


async def test_sse_endpoint():
    """Test SSE endpoint with a real HTTP client."""
    print("\n" + "=" * 60)
    print("Test 4: SSE endpoint test (requires running server)")
    print("=" * 60)
    print("Skipping - run manually with server running")


def test_buffer_limits():
    """Test that buffer limits are sufficient."""
    print("\n" + "=" * 60)
    print("Test 5: Buffer limits test")
    print("=" * 60)

    from task_manager import TaskManager

    # Create fresh instance
    TaskManager._instance = None
    manager = TaskManager()

    print(f"Output buffer maxlen: {manager.output_buffer.maxlen}")
    assert manager.output_buffer.maxlen >= 2000, "Output buffer should be >= 2000"

    # Test queue creation
    queue = manager.subscribe()
    print(f"SSE queue maxsize: {queue.maxsize}")
    assert queue.maxsize >= 2000, "SSE queue should be >= 2000"

    print("Buffer limits OK!")


if __name__ == "__main__":
    print("Lyric Transcribe - Streaming Tests")
    print("=" * 60)

    # Check ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("ffmpeg: OK")
    except Exception as e:
        print(f"ffmpeg: NOT FOUND - {e}")
        sys.exit(1)

    # Run tests
    test_buffer_limits()
    test_transcriber_callback()
    asyncio.run(test_task_manager_streaming())
    asyncio.run(test_many_events())

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
