"""Main Stockpile class for orchestrating the entire workflow."""

import logging
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
    """Central orchestrator for Stockpile."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the Stockpile with configuration."""
        self.config = config or load_config()
        self.processing_files: Set[str] = set()
        self.event_loop = None

        # Validate configuration
        config_errors = validate_config(self.config)
        if config_errors:
            error_msg = "Configuration errors: " + "; ".join(config_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Initialize services
        whisper_model = self.config.get("whisper_model", "base")
        self.transcription_service = TranscriptionService(whisper_model)

        gemini_api_key = self.config.get("gemini_api_key")
        if not gemini_api_key:
            raise ValueError("Gemini API key is required")
        gemini_model = self.config.get("gemini_model", "gemini-2.0-flash-001")
        self.ai_service = AIService(gemini_api_key, gemini_model)

        max_videos_per_phrase = self.config.get("max_videos_per_phrase", 3)
        self.youtube_service = YouTubeService(max_results=max_videos_per_phrase * 3)

        output_dir = self.config.get("local_output_folder", "../output")
        self.video_downloader = VideoDownloader(output_dir)
        self.file_organizer = FileOrganizer(output_dir)

        # Initialize notification service if Google credentials are configured
        client_id = self.config.get("google_client_id")
        client_secret = self.config.get("google_client_secret")
        if client_id and client_secret:
            notification_email = self.config.get("notification_email")
            self.notification_service = NotificationService(
                client_id, client_secret, notification_email
            )
        else:
            self.notification_service = None

        # Initialize Google Drive service if configured
        output_folder_id = self.config.get("google_drive_output_folder_id")
        if output_folder_id:
            client_id = self.config.get("google_client_id")
            client_secret = self.config.get("google_client_secret")
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

        # Initialize file monitor
        self.file_monitor = FileMonitor(self.config, self._handle_new_file)

        logger.info("Stockpile initialized successfully")

    def start(self) -> None:
        """Start the processor."""
        logger.info("Starting Stockpile...")

        # Store the event loop for cross-thread task scheduling
        self.event_loop = asyncio.get_running_loop()

        # Start file monitoring
        self.file_monitor.start_monitoring()

        logger.info("Processor started successfully")

    def _handle_new_file(self, file_path: str, source: str) -> None:
        """Handle new file detected by file monitor."""
        logger.info(f"New file detected from {source}: {file_path}")

        # Check for duplicate processing
        if file_path in self.processing_files:
            logger.info(f"File already being processed: {file_path}")
            return

        # Start processing the file asynchronously using the stored event loop
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

        # Add to processing set
        self.processing_files.add(file_path)
        logger.info(f"Starting processing: {file_path}")

        try:
            # Execute processing pipeline
            await self._execute_pipeline(file_path)
            logger.info(f"Processing completed successfully: {file_path}")

        except Exception as e:
            logger.error(f"Processing failed for {file_path}: {e}")
            await self._send_notification(file_path, "failed", str(e))
            raise

        finally:
            # Remove from processing set
            self.processing_files.discard(file_path)

    async def _execute_pipeline(self, file_path: str) -> None:
        """Execute the complete processing pipeline for a file."""
        logger.info(f"Starting pipeline for: {file_path}")

        # Step 1: Transcribe audio
        logger.info(f"Transcribing: {file_path}")
        transcript = await self.transcribe_audio(file_path)
        logger.info(f"Transcription completed. Length: {len(transcript)} characters")

        # Step 2: Extract search phrases
        search_phrases = await self.extract_search_phrases(transcript)
        logger.info(f"Extracted {len(search_phrases)} search phrases: {search_phrases}")

        # Step 3: Create project folder structure
        source_filename = Path(file_path).name
        project_dir = await self._create_project_structure(
            file_path, source_filename, search_phrases
        )
        logger.info(f"Project structure created: {project_dir}")

        # Step 3.5: Create Drive folder structure if Drive service is enabled
        drive_folder_structure = {}
        drive_folder_url = None
        if self.drive_service and source_filename:
            project_name = self._generate_project_name(file_path, source_filename)
            loop = asyncio.get_event_loop()
            drive_folder_structure = await loop.run_in_executor(
                None,
                self.drive_service.create_project_structure,
                project_name,
                search_phrases,
            )
            drive_folder_url = f"https://drive.google.com/drive/folders/{drive_folder_structure.get('project_id', '')}"
            logger.info(f"Google Drive structure created: {drive_folder_url}")

        # Step 4: Search and download B-roll for each phrase
        logger.info(f"Processing {len(search_phrases)} search phrases")
        phrase_downloads = {}
        for phrase in search_phrases:
            logger.info(f"Processing phrase: {phrase}")

            # Search YouTube
            video_results = await self.search_youtube_videos(phrase)
            logger.info(f"Found {len(video_results)} videos for: {phrase}")

            # Evaluate videos
            scored_videos = await self.evaluate_videos(phrase, video_results)
            logger.info(f"Selected {len(scored_videos)} top videos for: {phrase}")

            # Download videos directly to project folder
            phrase_folder = Path(
                project_dir
            ) / self.file_organizer._sanitize_folder_name(phrase)

            # Get Drive folder ID if Drive service is enabled
            drive_phrase_folder_id = None
            if self.drive_service and drive_folder_structure:
                drive_phrase_folder_id = drive_folder_structure.get(
                    "phrase_folders", {}
                ).get(phrase)

            # Download videos with optional immediate upload
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

        # Step 5: Send notification
        total_videos = sum(len(files) for files in phrase_downloads.values())
        message = f"Successfully processed {len(search_phrases)} phrases and downloaded {total_videos} videos"
        await self._send_notification(
            file_path, "completed", message, project_dir, drive_folder_url
        )

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio content using Whisper."""
        # Check if file format is supported
        if not self.transcription_service.is_supported_file(file_path):
            raise ValueError(f"Unsupported file format: {Path(file_path).suffix}")

        # Run transcription with concurrency protection
        transcript = await self.transcription_service.transcribe_audio(file_path)
        return transcript

    async def extract_search_phrases(self, transcript: str) -> List[str]:
        """Extract relevant search phrases using Gemini AI."""
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript provided for phrase extraction")
            return []

        # Run AI phrase extraction in thread pool to avoid blocking
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

        # Run YouTube search in thread pool to avoid blocking
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

        # Run AI video evaluation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        scored_videos = await loop.run_in_executor(
            None, self.ai_service.evaluate_videos, phrase, videos
        )

        # Limit to max videos per phrase
        max_videos = self.config.get("max_videos_per_phrase", 3)
        limited_videos = scored_videos[:max_videos]
        return limited_videos

    async def _create_project_structure(
        self, file_path: str, source_filename: str, phrases: List[str]
    ) -> str:
        """Create the project folder structure upfront."""
        # Run project creation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        project_path = await loop.run_in_executor(
            None,
            self.file_organizer.create_project_structure,
            file_path,  # Use file_path as unique identifier
            source_filename,
            phrases,
        )
        return project_path

    def _generate_project_name(self, file_path: str, source_filename: str) -> str:
        """Generate a consistent project name for both local and Drive folders."""
        from datetime import datetime
        import hashlib

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create a short hash from file path for uniqueness
        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]

        if source_filename:
            source_base = Path(source_filename).stem
            source_base = self.file_organizer._sanitize_folder_name(source_base)[:30]
            return f"stockpile_{source_base}_{file_hash}_{timestamp}"
        else:
            return f"stockpile_project_{file_hash}_{timestamp}"

    async def _send_notification(
        self,
        file_path: str,
        status: str,
        message: str,
        output_path: Optional[str] = None,
        drive_folder_url: Optional[str] = None,
    ) -> None:
        """Send email notification about processing completion."""
        if not self.notification_service:
            logger.debug("Email notifications not configured, skipping notification")
            return

        logger.info(f"Sending notification for {file_path}: {status} - {message}")

        # Run email sending in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self.notification_service.send_notification,
                file_path,  # Use file_path as identifier
                status,
                message,
                output_path,
                drive_folder_url,
                None,  # processing_time - could calculate if needed
                file_path,  # input_file
                None,  # video_count - could calculate if needed
            )
            logger.info(f"Email notification sent for {file_path}")
        except Exception as e:
            logger.error(f"Failed to send email notification for {file_path}: {e}")
