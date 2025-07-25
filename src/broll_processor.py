"""Main stockpile class for orchestrating the entire workflow."""

import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
import asyncio

from models.video import VideoResult, ScoredVideo
from utils.config import load_config, validate_config
from services.transcription import TranscriptionService
from services.ai_service import AIService
from services.youtube_service import YouTubeService
from services.video_downloader import VideoDownloader
from services.file_organizer import FileOrganizer
from services.notification import NotificationService
from services.drive_service import DriveService
from services.file_monitor import FileMonitor

logger = logging.getLogger(__name__)


class BRollProcessor:
    """Central orchestrator for stockpile."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the stockpile with configuration."""
        self.config = config or load_config()
        self.processing_files: Set[str] = set()
        self.event_loop = None

        config_errors = validate_config(self.config)
        if config_errors:
            error_msg = "Configuration errors: " + "; ".join(config_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

        gemini_api_key = self.config.get("gemini_api_key")
        if not gemini_api_key:
            raise ValueError("Gemini API key is required")
        gemini_model = self.config.get("gemini_model", "gemma-3-27b-it")
        self.ai_service = AIService(gemini_api_key, gemini_model)

        client_id = self.config.get("google_client_id")
        client_secret = self.config.get("google_client_secret")
        if client_id and client_secret:
            notification_email = self.config.get("notification_email")
            self.notification_service = NotificationService(
                client_id, client_secret, notification_email
            )
        else:
            self.notification_service = None

        max_videos_per_phrase = self.config.get("max_videos_per_phrase", 3)
        self.youtube_service = YouTubeService(max_results=max_videos_per_phrase * 3)

        whisper_model = self.config.get("whisper_model", "base")
        self.transcription_service = TranscriptionService(whisper_model)

        output_dir = self.config.get("local_output_folder", "../output")
        self.video_downloader = VideoDownloader(output_dir)
        self.file_organizer = FileOrganizer(output_dir)

        output_folder_id = self.config.get("google_drive_output_folder_id")
        if output_folder_id:
            if not client_id:
                raise ValueError(
                    "Google Drive requires GOOGLE_CLIENT_ID environment variable"
                )
            if not client_secret:
                raise ValueError(
                    "Google Drive requires GOOGLE_CLIENT_SECRET environment variable"
                )
            self.drive_service = DriveService(
                client_id, client_secret, output_folder_id
            )
        else:
            self.drive_service = None

        self.file_monitor = FileMonitor(self.config, self._handle_new_file)

        logger.info("stockpile initialized successfully")

    def start(self) -> None:
        """Start the processor."""
        logger.info("Starting stockpile...")

        self.event_loop = asyncio.get_running_loop()

        self.file_monitor.start_monitoring()

        logger.info("Processor started successfully")

    def _handle_new_file(self, file_path: str, source: str) -> None:
        """Handle new file detected by file monitor."""
        logger.info(f"New file detected from {source}: {file_path}")

        if file_path in self.processing_files:
            return

        if self.event_loop and not self.event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self.process_video(file_path), self.event_loop
            )
        else:
            logger.error("No event loop available to schedule file processing")

    async def process_video(self, file_path: str) -> None:
        """Process a video file through the complete B-roll pipeline."""
        if file_path in self.processing_files:
            logger.info(f"File already being processed: {file_path}")
            return

        self.processing_files.add(file_path)

        start_time = time.time()

        try:
            await self._execute_pipeline(file_path, start_time)
            logger.info(f"Processing completed successfully: {file_path}")

        except Exception as e:
            logger.error(f"Processing failed for {file_path}: {e}")
            processing_time = self._format_processing_time(time.time() - start_time)
            await self._send_notification(
                "failed", str(e), processing_time=processing_time, input_file=file_path
            )
            raise

        finally:
            self.processing_files.discard(file_path)

    async def _execute_pipeline(self, file_path: str, start_time: float) -> None:
        """Execute the complete processing pipeline for a file."""
        logger.info(f"Starting pipeline for: {file_path}")

        transcript = await self.transcribe_audio(file_path)
        logger.info(f"Transcription completed. Length: {len(transcript)} characters")

        search_phrases = await self.extract_search_phrases(transcript)
        logger.info(f"Extracted {len(search_phrases)} search phrases: {search_phrases}")

        source_filename = Path(file_path).name
        project_dir = await self._create_project_structure(file_path, source_filename)
        logger.info(f"Project structure created: {project_dir}")

        drive_project_folder_id = None
        drive_folder_url = None
        if self.drive_service and source_filename:
            project_name = self._generate_project_name(file_path, source_filename)
            loop = asyncio.get_event_loop()
            drive_project_folder_id = await loop.run_in_executor(
                None,
                self.drive_service.create_project_structure,
                project_name,
            )
            drive_folder_url = (
                f"https://drive.google.com/drive/folders/{drive_project_folder_id}"
            )
            logger.info(f"Google Drive structure created: {drive_folder_url}")

        logger.info(f"Processing {len(search_phrases)} search phrases")
        phrase_downloads = {}
        for phrase in search_phrases:
            logger.info(f"Processing phrase: {phrase}")

            video_results = await self.search_youtube_videos(phrase)
            logger.info(f"Found {len(video_results)} videos for: {phrase}")

            scored_videos = await self.evaluate_videos(phrase, video_results)
            logger.info(f"Selected {len(scored_videos)} top videos for: {phrase}")

            # Skip if no videos to download
            if not scored_videos:
                logger.info(f"No videos to download for phrase: {phrase}")
                continue

            phrase_folder = Path(
                project_dir
            ) / self.file_organizer._sanitize_folder_name(phrase)

            drive_phrase_folder_id = None
            if self.drive_service:
                # Create phrase folder on-demand
                loop = asyncio.get_event_loop()
                drive_phrase_folder_id = await loop.run_in_executor(
                    None,
                    self.drive_service.create_phrase_folder,
                    phrase,
                    drive_project_folder_id,
                )

            loop = asyncio.get_event_loop()
            downloaded_files = await loop.run_in_executor(
                None,
                self.video_downloader.download_videos_to_folder,
                scored_videos,
                phrase,
                str(phrase_folder),
                self.drive_service,
                drive_phrase_folder_id,
            )
            phrase_downloads[phrase] = downloaded_files
            logger.info(f"Downloaded {len(downloaded_files)} files for: {phrase}")

        total_videos = sum(len(files) for files in phrase_downloads.values())

        # Clean up any empty directories that may have been created
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.file_organizer._cleanup_empty_directories,
        )

        processing_time = self._format_processing_time(time.time() - start_time)
        await self._send_notification(
            "completed",
            project_dir,
            drive_folder_url,
            processing_time,
            file_path,
            total_videos,
        )

        # Clean up local output if Google Drive is configured
        if self.drive_service and project_dir:
            await self._cleanup_local_output(project_dir)

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio content using Whisper."""
        if not self.transcription_service.is_supported_file(file_path):
            raise ValueError(f"Unsupported file format: {Path(file_path).suffix}")

        transcript = await self.transcription_service.transcribe_audio(file_path)
        return transcript

    async def extract_search_phrases(self, transcript: str) -> List[str]:
        """Extract relevant search phrases using Gemini AI."""
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript provided for phrase extraction")
            return []

        loop = asyncio.get_event_loop()
        search_phrases = await loop.run_in_executor(
            None, self.ai_service.extract_search_phrases, transcript
        )
        return search_phrases

    async def search_youtube_videos(self, phrase: str) -> List[VideoResult]:
        """Search YouTube for videos matching the phrase."""
        if not phrase or not phrase.strip():
            logger.warning("Empty search phrase provided")
            return []

        loop = asyncio.get_event_loop()
        video_results = await loop.run_in_executor(
            None, self.youtube_service.search_videos, phrase
        )
        return video_results

    async def evaluate_videos(
        self, phrase: str, videos: List[VideoResult]
    ) -> List[ScoredVideo]:
        """Evaluate videos using Gemini AI."""
        if not videos:
            logger.info(f"No videos to evaluate for phrase: {phrase}")
            return []

        loop = asyncio.get_event_loop()
        scored_videos = await loop.run_in_executor(
            None, self.ai_service.evaluate_videos, phrase, videos
        )

        max_videos = self.config.get("max_videos_per_phrase", 3)
        limited_videos = scored_videos[:max_videos]
        return limited_videos

    async def _create_project_structure(
        self, file_path: str, source_filename: str
    ) -> str:
        """Create the project folder structure upfront."""
        loop = asyncio.get_event_loop()
        project_path = await loop.run_in_executor(
            None,
            self.file_organizer.create_project_structure,
            file_path,
            source_filename,
        )
        return project_path

    def _generate_project_name(self, file_path: str, source_filename: str) -> str:
        """Generate a consistent project name for both local and Drive folders."""
        from datetime import datetime
        import hashlib

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]

        if source_filename:
            source_base = Path(source_filename).stem
            source_base = self.file_organizer._sanitize_folder_name(source_base)[:30]
            return f"{source_base}_{file_hash}_{timestamp}"
        else:
            return f"{file_hash}_{timestamp}"

    def _format_processing_time(self, seconds: float) -> str:
        """Format processing time in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            return f"{seconds/60:.1f} minutes"
        else:
            return f"{seconds/3600:.1f} hours"

    async def _send_notification(
        self,
        status: str,
        output_path: Optional[str] = None,
        drive_folder_url: Optional[str] = None,
        processing_time: Optional[str] = None,
        input_file: Optional[str] = None,
        video_count: Optional[int] = None,
    ) -> None:
        """Send email notification about processing completion."""
        if not self.notification_service:
            logger.debug("Email notifications not configured, skipping notification")
            return

        logger.info(f"Sending notification: {status}")

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self.notification_service.send_notification,
                status,
                output_path,
                drive_folder_url,
                processing_time,
                input_file,
                video_count,
            )
            logger.info(f"Email notification sent: {status}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    async def _cleanup_local_output(self, project_dir: str) -> None:
        """Clean up local output directory after successful Drive upload."""
        import shutil

        try:
            if Path(project_dir).exists():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, shutil.rmtree, project_dir)
                logger.info(f"Cleaned up local output directory: {project_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up local directory {project_dir}: {e}")
