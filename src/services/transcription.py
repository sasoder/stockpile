"""Audio transcription service using OpenAI Whisper."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import whisper

from utils.retry import retry_api_call, retry_file_operation
from utils.config import get_supported_video_formats, get_supported_audio_formats

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for transcribing audio content using OpenAI Whisper."""
    
    def __init__(self, model_name: str = "base"):
        """Initialize Whisper model for audio transcription.
        
        Args:
            model_name: Whisper model size (tiny, base, small, medium, large, turbo)
        """
        self.model_name = model_name
        self.model = None
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the Whisper model."""
        try:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self.model = whisper.load_model(self.model_name)
            
            # Log model information
            is_multilingual = "multilingual" if self.model.is_multilingual else "English-only"
            param_count = sum(p.numel() for p in self.model.parameters())
            logger.info(f"Loaded {is_multilingual} Whisper model with {param_count:,} parameters")
            
        except Exception as e:
            logger.error(f"Failed to load Whisper model '{self.model_name}': {e}")
            raise
    
    @retry_api_call(max_retries=3, base_delay=2.0)
    def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio file to text.
        
        Args:
            file_path: Path to audio or video file
            
        Returns:
            Transcribed text content
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Starting transcription of: {file_path.name}")
        
        try:
            # Check if we need to extract audio from video
            if self._is_video_file(file_path):
                audio_path = self._extract_audio_from_video(file_path)
                cleanup_audio = True
            else:
                audio_path = str(file_path)
                cleanup_audio = False
            
            # Transcribe using Whisper
            result = self._transcribe_with_whisper(audio_path)
            
            # Cleanup temporary audio file if created
            if cleanup_audio:
                Path(audio_path).unlink(missing_ok=True)
            
            logger.info(f"Transcription completed. Length: {len(result)} characters")
            return result
            
        except Exception as e:
            logger.error(f"Transcription failed for {file_path}: {e}")
            raise
    
    def _transcribe_with_whisper(self, audio_path: str) -> str:
        """Perform the actual transcription using Whisper.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Transcribed text
        """
        try:
            # Load and preprocess audio
            audio = whisper.load_audio(audio_path)
            audio = whisper.pad_or_trim(audio)
            
            # Create mel spectrogram
            mel = whisper.log_mel_spectrogram(audio, n_mels=self.model.dims.n_mels).to(self.model.device)
            
            # Detect language
            _, probs = self.model.detect_language(mel)
            detected_language = max(probs, key=probs.get)
            confidence = probs[detected_language]
            
            logger.info(f"Detected language: {detected_language} (confidence: {confidence:.2f})")
            
            # Set up decoding options
            options = whisper.DecodingOptions(
                language=detected_language if confidence > 0.5 else "en",
                without_timestamps=True,
                fp16=False  # Use fp32 for better compatibility
            )
            
            # Decode audio
            result = whisper.decode(self.model, mel, options)
            
            return result.text.strip()
            
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
        
        # Create temporary audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_path = temp_file.name
        
        try:
            # Use ffmpeg to extract audio
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # PCM 16-bit little-endian
                '-ar', '16000',  # 16kHz sample rate (Whisper's preferred rate)
                '-ac', '1',  # Mono audio
                '-y',  # Overwrite output file
                audio_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.debug(f"Audio extraction completed: {audio_path}")
            return audio_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr}")
            # Cleanup failed extraction
            Path(audio_path).unlink(missing_ok=True)
            raise RuntimeError(f"Audio extraction failed: {e.stderr}")
        
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            # Cleanup on any error
            Path(audio_path).unlink(missing_ok=True)
            raise
    
    def _is_video_file(self, file_path: Path) -> bool:
        """Check if file is a video format that needs audio extraction.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is a video format
        """
        video_extensions = get_supported_video_formats()
        return file_path.suffix.lower() in video_extensions
    
    def _is_audio_file(self, file_path: Path) -> bool:
        """Check if file is an audio format.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is an audio format
        """
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
    
