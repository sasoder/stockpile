"""Audio transcription service using OpenAI Whisper."""

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
import whisper

from utils.retry import retry_api_call, retry_file_operation
from utils.config import get_supported_video_formats, get_supported_audio_formats

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for transcribing audio content using OpenAI Whisper."""

    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self.model = None
        self._transcription_lock = asyncio.Lock()
        self._load_model()

    def _load_model(self) -> None:
        try:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self.model = whisper.load_model(self.model_name)

            is_multilingual = (
                "multilingual" if self.model.is_multilingual else "English-only"
            )
            param_count = sum(p.numel() for p in self.model.parameters())
            logger.info(
                f"Loaded {is_multilingual} Whisper model with {param_count:,} parameters"
            )

        except Exception as e:
            logger.error(f"Failed to load Whisper model '{self.model_name}': {e}")
            raise

    @retry_api_call(max_retries=3, base_delay=2.0)
    async def transcribe_audio(self, input_file_path: str) -> str:
        """Transcribe audio file to text.

        Args:
            file_path: Path to audio or video file

        Returns:
            Transcribed text content
        """
        file_path: Path = Path(input_file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Starting transcription of: {file_path.name}")

        try:
            if self._is_video_file(file_path):
                audio_path = self._extract_audio_from_video(file_path)
                cleanup_audio = True
            else:
                audio_path = file_path
                cleanup_audio = False

            async with self._transcription_lock:
                result = await asyncio.to_thread(
                    self._transcribe_with_whisper, str(audio_path)
                )

            if cleanup_audio:
                Path(audio_path).unlink(missing_ok=True)

            return result

        except Exception as e:
            logger.error(f"Transcription failed for {file_path}: {e}")
            raise

    def _transcribe_with_whisper(self, audio_path: str) -> str:
        try:
            if not self.model:
                raise ValueError("Whisper model not loaded")
            result = self.model.transcribe(
                str(audio_path),
                language=None,
                task="transcribe",
                fp16=False,
                verbose=False,
            )

            text = result.get("text", "")
            if isinstance(text, str):
                return text.strip()
            else:
                raise ValueError("Transcription result is not a string")

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise

    @retry_file_operation(max_retries=3, base_delay=1.0)
    def _extract_audio_from_video(self, video_path: Path) -> str:
        """Extract audio from video file using ffmpeg.

        Args:
            video_path: Path to video file

        Returns:
            Path to extracted audio file
        """
        logger.info(f"Extracting audio from video: {video_path.name}")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            audio_path = temp_file.name

        try:
            cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-y",
                audio_path,
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            logger.debug(f"Audio extraction completed: {audio_path}")
            return audio_path

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr}")
            Path(audio_path).unlink(missing_ok=True)
            raise RuntimeError(f"Audio extraction failed: {e.stderr}")

        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            Path(audio_path).unlink(missing_ok=True)
            raise

    def _is_video_file(self, file_path: Path) -> bool:
        video_extensions = get_supported_video_formats()
        return file_path.suffix.lower() in video_extensions

    def _is_audio_file(self, file_path: Path) -> bool:
        audio_extensions = get_supported_audio_formats()
        return file_path.suffix.lower() in audio_extensions

    def is_supported_file(self, file_path: str) -> bool:
        """Check if file format is supported for transcription.

        Args:
            file_path: Path to file

        Returns:
            True if file format is supported
        """
        path = Path(file_path)
        return self._is_video_file(path) or self._is_audio_file(path)
