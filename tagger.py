"""ID3 tag embedding for MP3 files."""

import subprocess
import tempfile
from pathlib import Path

from mutagen.id3 import ID3, APIC, SYLT, TIT2, TPE1, TALB, Encoding
from mutagen.mp3 import MP3


def parse_lrc(lrc_path: str) -> list[tuple[str, int]]:
    """
    Parse LRC file and return list of (text, time_ms) tuples for SYLT.

    Args:
        lrc_path: Path to the LRC file

    Returns:
        List of (text, milliseconds) tuples (SYLT format)
    """
    lyrics = []
    with open(lrc_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith("["):
                continue

            # Parse timestamp [mm:ss.xx]
            try:
                bracket_end = line.index("]")
                timestamp = line[1:bracket_end]
                text = line[bracket_end + 1:].strip()

                if not text:
                    continue

                # Parse mm:ss.xx format
                parts = timestamp.split(":")
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = float(parts[1])
                    time_ms = int((minutes * 60 + seconds) * 1000)
                    # SYLT format: (text, time_ms)
                    lyrics.append((text, time_ms))
            except (ValueError, IndexError):
                continue

    return lyrics


def embed_lyric(
    audio_path: str,
    lyric_path: str,
    output_path: str,
    singer: str = "",
    album: str = "",
    cover_path: str = "",
    title: str = "",
) -> bool:
    """
    Embed lyrics and metadata into MP3 file.

    Args:
        audio_path: Path to the source audio file
        lyric_path: Path to the LRC file
        output_path: Path for the output MP3 file
        singer: Artist name
        album: Album name
        cover_path: Path to cover image
        title: Song title (defaults to filename without extension)

    Returns:
        True if successful, False otherwise
    """
    audio_path = Path(audio_path)
    lyric_path = Path(lyric_path)
    output_path = Path(output_path)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use filename as title if not provided
    if not title:
        title = audio_path.stem

    # Convert to MP3 if not already
    if audio_path.suffix.lower() != ".mp3":
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
            tmp_mp3_path = tmp_mp3.name

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", str(audio_path),
                    "-codec:a", "libmp3lame",
                    "-qscale:a", "2",
                    "-y",
                    tmp_mp3_path,
                ],
                check=True,
                capture_output=True,
            )

            # Move to final location
            import shutil
            shutil.move(tmp_mp3_path, str(output_path))
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg conversion failed: {e.stderr.decode()}") from e
    else:
        # Copy MP3 directly
        import shutil
        shutil.copy2(str(audio_path), str(output_path))

    # Load MP3 and add ID3 tags
    try:
        audio = MP3(str(output_path))
        if audio.tags is None:
            audio.add_tags()
    except Exception:
        audio = MP3(str(output_path))
        audio.add_tags()

    tags = audio.tags

    # Add basic metadata
    tags.add(TIT2(encoding=Encoding.UTF8, text=title))

    if singer:
        tags.add(TPE1(encoding=Encoding.UTF8, text=singer))

    if album:
        tags.add(TALB(encoding=Encoding.UTF8, text=album))

    # Add synchronized lyrics (SYLT)
    lyrics = parse_lrc(str(lyric_path))
    if lyrics:
        sylt = SYLT(
            encoding=Encoding.UTF8,
            lang="zho",
            format=2,  # milliseconds
            type=1,    # lyrics
            text=lyrics,
        )
        tags.add(sylt)

    # Add cover art if provided
    if cover_path and Path(cover_path).exists():
        cover_path = Path(cover_path)
        mime_type = "image/jpeg"
        if cover_path.suffix.lower() == ".png":
            mime_type = "image/png"

        with open(cover_path, "rb") as f:
            cover_data = f.read()

        tags.add(
            APIC(
                encoding=Encoding.UTF8,
                mime=mime_type,
                type=3,  # Cover (front)
                desc="Cover",
                data=cover_data,
            )
        )

    audio.save()
    return True
