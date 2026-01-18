"""Audio transcription using pywhispercpp."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from pywhispercpp.model import Model


def format_timestamp(seconds: float) -> str:
    """Format seconds to LRC timestamp [mm:ss.xx]."""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"[{minutes:02d}:{secs:05.2f}]"


def transcribe_audio(
    audio_path: str,
    output_lrc_path: str,
    model: str = "large-v3-turbo",
    language: str = "zh",
    prompt: str = "歌词 简体中文",
    callback: Callable[[str, str], None] | None = None,
) -> bool:
    """
    Transcribe audio file to LRC format.

    Args:
        audio_path: Path to the source audio file
        output_lrc_path: Path for the output LRC file
        model: Whisper model name
        language: Language code for transcription
        prompt: Initial prompt for better transcription
        callback: Optional callback for progress updates (time, text)

    Returns:
        True if successful, False otherwise
    """
    audio_path = Path(audio_path)
    output_lrc_path = Path(output_lrc_path)

    # Ensure output directory exists
    output_lrc_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert audio to WAV format for whisper
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        tmp_wav_path = tmp_wav.name

    # Collect all lines for final LRC file
    lrc_lines = []

    def on_new_segment(segment):
        """Callback for real-time segment processing."""
        start_time = segment.t0 / 100.0  # Convert to seconds
        text = segment.text.strip()

        if text:
            timestamp = format_timestamp(start_time)
            lrc_line = f"{timestamp}{text}"
            lrc_lines.append(lrc_line)

            # Notify progress in real-time
            if callback:
                callback(timestamp, text)

    try:
        # Convert to WAV using ffmpeg
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(audio_path),
                "-ar", "16000",
                "-ac", "1",
                "-y",
                tmp_wav_path,
            ],
            check=True,
            capture_output=True,
        )

        # Initialize whisper model with real-time output disabled
        whisper = Model(model, print_realtime=False, print_progress=False)

        # Set parameters for transcription
        params = {
            "no_context": True,
            "n_max_text_ctx": 0,
            "n_threads": 8,
        }

        # Transcribe with real-time callback
        whisper.transcribe(
            tmp_wav_path,
            language=language,
            initial_prompt=prompt,
            new_segment_callback=on_new_segment,
            **params
        )

        # Write LRC file
        with open(output_lrc_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lrc_lines))

        return True

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr.decode()}") from e
    except Exception as e:
        raise RuntimeError(f"Transcription failed: {str(e)}") from e
    finally:
        # Cleanup temp file
        if os.path.exists(tmp_wav_path):
            os.unlink(tmp_wav_path)


def get_available_models() -> list[str]:
    """Get list of available whisper models."""
    return [
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large-v1",
        "large-v2",
        "large-v3",
        "large-v3-turbo",
    ]
