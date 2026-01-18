"""Audio merger module using FFmpeg."""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class AudioMerger:
    """Handle audio file merging using FFmpeg."""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.cancelled = False

    async def merge_audio_files(
        self,
        source_files: List[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> bool:
        """
        Merge multiple audio files into a single WAV file using FFmpeg.

        Args:
            source_files: List of source audio file paths
            output_path: Output file path (should end with .wav)
            progress_callback: Optional callback for progress updates

        Returns:
            True if successful, False otherwise
        """
        if not source_files:
            logger.error("No source files provided")
            return False

        if len(source_files) < 2:
            logger.error("At least 2 files required for merging")
            return False

        # Ensure output is WAV
        if not str(output_path).endswith('.wav'):
            output_path = output_path.with_suffix('.wav')

        try:
            # Create temporary file list for FFmpeg
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False, encoding='utf-8'
            ) as temp_file:
                filelist_path = temp_file.name
                for source_file in source_files:
                    # Escape single quotes in filenames
                    escaped_path = str(source_file).replace("'", "'\\''")
                    temp_file.write(f"file '{escaped_path}'\n")

            logger.info(f"Merging {len(source_files)} files into {output_path}")

            if progress_callback:
                progress_callback({
                    'percentage': 10,
                    'message': f'正在准备合并 {len(source_files)} 个文件...'
                })

            # Build FFmpeg command
            # Using concat demuxer for better compatibility
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', filelist_path,
                '-c:a', 'pcm_s16le',  # WAV format, 16-bit PCM
                '-ar', '44100',       # 44.1kHz sample rate
                '-y',                 # Overwrite output file
                str(output_path)
            ]

            logger.info(f"Running command: {' '.join(cmd)}")

            if progress_callback:
                progress_callback({
                    'percentage': 20,
                    'message': '正在启动 FFmpeg...'
                })

            # Run FFmpeg
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            if progress_callback:
                progress_callback({
                    'percentage': 30,
                    'message': '正在合并音频文件...'
                })

            # Read output
            stderr_output = []
            line_count = 0
            if self.process.stderr:
                for line in self.process.stderr:
                    if self.cancelled:
                        self.process.terminate()
                        logger.info("Merge cancelled by user")
                        return False

                    stderr_output.append(line)
                    logger.debug(f"FFmpeg: {line.strip()}")
                    line_count += 1

                    # Send progress updates periodically
                    if line_count % 5 == 0 and progress_callback:
                        # Gradually increase progress from 30% to 90%
                        progress_pct = min(90, 30 + (line_count * 2))
                        progress_callback({
                            'percentage': progress_pct,
                            'message': '正在合并音频文件...'
                        })

            # Wait for completion
            returncode = self.process.wait()

            # Clean up temporary file
            try:
                os.unlink(filelist_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")

            if returncode != 0:
                error_msg = '\n'.join(stderr_output[-10:])  # Last 10 lines
                logger.error(f"FFmpeg failed with code {returncode}: {error_msg}")
                return False

            if progress_callback:
                progress_callback({
                    'percentage': 100,
                    'message': '合并完成'
                })

            logger.info(f"Successfully merged to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error merging audio files: {e}")
            return False
        finally:
            self.process = None

    def cancel(self):
        """Cancel the current merge operation."""
        self.cancelled = True
        if self.process:
            try:
                self.process.terminate()
                logger.info("Merge process terminated")
            except Exception as e:
                logger.error(f"Error terminating process: {e}")

    @staticmethod
    def check_file_exists(path: Path) -> bool:
        """Check if a file exists."""
        return path.exists()

    @staticmethod
    async def delete_source_files(files: List[Path]) -> None:
        """Delete source files after successful merge."""
        for file_path in files:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Deleted source file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")

    @staticmethod
    def check_ffmpeg_installed() -> bool:
        """Check if FFmpeg is installed and available."""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
