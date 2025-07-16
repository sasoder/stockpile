"""Main B-Roll Processor class for orchestrating the entire workflow."""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import asyncio

from .models.job import ProcessingJob, JobStatus
from .models.video import VideoResult, ScoredVideo
from .utils.database import init_database, save_job_progress, load_incomplete_jobs
from .utils.config import load_config, validate_config
from .utils.retry import retry_api_call, retry_file_operation
from .services.transcription import TranscriptionService
from .services.ai_service import AIService
from .services.youtube_service import YouTubeService
from .services.video_downloader import VideoDownloader
from .services.file_organizer import FileOrganizer
from .services.notification import NotificationService
from .services.drive_service import DriveService

logger = logging.getLogger(__name__)


class BRollProcessor:
    """Central orchestrator for B-roll video processing workflow."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the B-Roll Processor with configuration."""
        self.config = config or load_config()
        self.db_path = self.config.get('database_path', 'broll_jobs.db')
        self.job_queue: List[ProcessingJob] = []
        self.processing_jobs: Dict[str, ProcessingJob] = {}
        
        # Initialize database
        init_database(self.db_path)
        
        # Validate configuration
        config_errors = validate_config(self.config)
        if config_errors:
            error_msg = "Configuration errors: " + "; ".join(config_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Initialize services
        whisper_model = self.config.get('whisper_model', 'base')
        self.transcription_service = TranscriptionService(whisper_model)
        
        gemini_api_key = self.config.get('gemini_api_key')
        gemini_model = self.config.get('gemini_model', 'gemini-2.0-flash-001')
        self.ai_service = AIService(gemini_api_key, gemini_model)
        
        max_videos_per_phrase = self.config.get('max_videos_per_phrase', 3)
        self.youtube_service = YouTubeService(max_results=max_videos_per_phrase * 3)
        
        output_dir = self.config.get('local_output_folder', './broll_output')
        self.video_downloader = VideoDownloader(output_dir)
        self.file_organizer = FileOrganizer(output_dir)
        
        # Initialize notification service if Gmail is configured
        gmail_user = self.config.get('gmail_user')
        gmail_password = self.config.get('gmail_password')
        if gmail_user and gmail_password:
            self.notification_service = NotificationService(gmail_user, gmail_password)
        else:
            self.notification_service = None
        
        # Initialize Google Drive service if configured
        drive_credentials_path = self.config.get('google_drive_credentials_path')
        if drive_credentials_path:
            self.drive_service = DriveService(drive_credentials_path)
        else:
            self.drive_service = None
        
        logger.info("B-Roll Processor initialized successfully")
    
    def start(self) -> None:
        """Start the processor and resume incomplete jobs."""
        logger.info("Starting B-Roll Processor...")
        
        # Resume incomplete jobs
        self.resume_incomplete_jobs()
        
        logger.info(f"Processor started with {len(self.job_queue)} jobs in queue")
    
    def create_job(self, file_path: str, source: str) -> str:
        """Create a new processing job and add to queue."""
        job_id = str(uuid.uuid4())
        now = datetime.now()
        
        job = ProcessingJob(
            job_id=job_id,
            file_path=file_path,
            source=source,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now
        )
        
        # Save to database
        save_job_progress(job, self.db_path)
        
        # Add to queue
        self.job_queue.append(job)
        
        logger.info(f"Created new job: {job_id} for file: {file_path}")
        return job_id
    
    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Get the current status of a job."""
        # Check processing jobs first
        if job_id in self.processing_jobs:
            return self.processing_jobs[job_id].status
        
        # Check queue
        for job in self.job_queue:
            if job.job_id == job_id:
                return job.status
        
        # Load from database
        from .utils.database import load_job
        job = load_job(job_id, self.db_path)
        return job.status if job else None
    
    def display_queue_status(self) -> None:
        """Display current queue status in terminal."""
        print("\n" + "="*60)
        print("B-ROLL PROCESSOR - QUEUE STATUS")
        print("="*60)
        
        # Show queue
        if self.job_queue:
            print(f"\nQueued Jobs ({len(self.job_queue)}):")
            for job in self.job_queue:
                print(f"  {job.job_id[:8]}... | {job.status.value:20} | {Path(job.file_path).name}")
        else:
            print("\nNo jobs in queue")
        
        # Show processing jobs
        if self.processing_jobs:
            print(f"\nProcessing Jobs ({len(self.processing_jobs)}):")
            for job in self.processing_jobs.values():
                print(f"  {job.job_id[:8]}... | {job.status.value:20} | {Path(job.file_path).name}")
        
        # Show recent completed jobs
        from .utils.database import get_recent_jobs
        recent_jobs = get_recent_jobs(self.db_path, limit=5)
        completed_jobs = [j for j in recent_jobs if j.status in [JobStatus.COMPLETED, JobStatus.FAILED]]
        
        if completed_jobs:
            print(f"\nRecent Completed Jobs ({len(completed_jobs)}):")
            for job in completed_jobs:
                status_symbol = "✓" if job.status == JobStatus.COMPLETED else "✗"
                print(f"  {status_symbol} {job.job_id[:8]}... | {job.status.value:20} | {Path(job.file_path).name}")
        
        print("="*60)
    
    def resume_incomplete_jobs(self) -> None:
        """Resume incomplete jobs from database on startup."""
        incomplete_jobs = load_incomplete_jobs(self.db_path)
        
        for job in incomplete_jobs:
            # Reset jobs that were in progress to queued state
            if job.status in [JobStatus.TRANSCRIBING, JobStatus.EXTRACTING_PHRASES, 
                             JobStatus.SEARCHING_YOUTUBE, JobStatus.DOWNLOADING, 
                             JobStatus.ORGANIZING, JobStatus.UPLOADING]:
                job.update_status(JobStatus.QUEUED)
                save_job_progress(job, self.db_path)
            
            self.job_queue.append(job)
        
        logger.info(f"Resumed {len(incomplete_jobs)} incomplete jobs")
    
    async def process_video(self, file_path: str, source: str) -> str:
        """Process a video file through the complete B-roll pipeline."""
        job_id = self.create_job(file_path, source)
        job = next(j for j in self.job_queue if j.job_id == job_id)
        
        try:
            # Move job to processing
            self.job_queue.remove(job)
            self.processing_jobs[job_id] = job
            
            # Execute processing pipeline
            await self._execute_pipeline(job)
            
            # Mark as completed
            job.update_status(JobStatus.COMPLETED)
            save_job_progress(job, self.db_path)
            
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            # Mark as failed
            job.update_status(JobStatus.FAILED, str(e))
            save_job_progress(job, self.db_path)
            
            logger.error(f"Job {job_id} failed: {e}")
            raise
        
        finally:
            # Remove from processing
            self.processing_jobs.pop(job_id, None)
        
        return job_id
    
    async def _execute_pipeline(self, job: ProcessingJob) -> None:
        """Execute the complete processing pipeline for a job."""
        logger.info(f"Starting pipeline for job {job.job_id}")
        
        # Step 1: Transcribe audio
        job.update_status(JobStatus.TRANSCRIBING)
        save_job_progress(job, self.db_path)
        transcript = await self.transcribe_audio(job.file_path)
        job.transcript = transcript
        save_job_progress(job, self.db_path)
        
        # Step 2: Extract search phrases
        job.update_status(JobStatus.EXTRACTING_PHRASES)
        save_job_progress(job, self.db_path)
        search_phrases = await self.extract_search_phrases(transcript)
        job.search_phrases = search_phrases
        save_job_progress(job, self.db_path)
        
        # Step 3: Search and download B-roll for each phrase
        job.update_status(JobStatus.SEARCHING_YOUTUBE)
        save_job_progress(job, self.db_path)
        
        phrase_downloads = {}
        for phrase in search_phrases:
            # Search YouTube
            video_results = await self.search_youtube_videos(phrase)
            
            # Evaluate videos
            scored_videos = await self.evaluate_videos(phrase, video_results)
            
            # Download top videos
            job.update_status(JobStatus.DOWNLOADING)
            save_job_progress(job, self.db_path)
            
            downloaded_files = await self.download_videos(scored_videos, phrase)
            phrase_downloads[phrase] = downloaded_files
        
        job.downloaded_files = phrase_downloads
        save_job_progress(job, self.db_path)
        
        # Step 4: Organize files
        job.update_status(JobStatus.ORGANIZING)
        save_job_progress(job, self.db_path)
        output_path = await self.organize_files(job.job_id, phrase_downloads)
        job.output_path = output_path
        save_job_progress(job, self.db_path)
        
        # Step 5: Upload to Google Drive if configured
        if self.config.get('google_drive_credentials_path'):
            job.update_status(JobStatus.UPLOADING)
            save_job_progress(job, self.db_path)
            await self.upload_to_drive(output_path, job.job_id)
        
        # Step 6: Send notification
        await self.send_notification(job.job_id, "completed", "Job completed successfully")
    
    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio content using Whisper."""
        logger.info(f"Starting transcription of: {file_path}")
        
        # Check if file format is supported
        if not self.transcription_service.is_supported_file(file_path):
            raise ValueError(f"Unsupported file format: {Path(file_path).suffix}")
        
        # Run transcription in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None, 
            self.transcription_service.transcribe_audio, 
            file_path
        )
        
        logger.info(f"Transcription completed. Length: {len(transcript)} characters")
        return transcript
    
    async def extract_search_phrases(self, transcript: str) -> List[str]:
        """Extract relevant search phrases using Gemini AI."""
        logger.info("Extracting search phrases from transcript")
        
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript provided for phrase extraction")
            return []
        
        # Run AI phrase extraction in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        search_phrases = await loop.run_in_executor(
            None,
            self.ai_service.extract_search_phrases,
            transcript
        )
        
        logger.info(f"Extracted {len(search_phrases)} search phrases: {search_phrases}")
        return search_phrases
    
    async def search_youtube_videos(self, phrase: str) -> List[VideoResult]:
        """Search YouTube for videos matching the phrase."""
        logger.info(f"Searching YouTube for: {phrase}")
        
        if not phrase or not phrase.strip():
            logger.warning("Empty search phrase provided")
            return []
        
        # Run YouTube search in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        video_results = await loop.run_in_executor(
            None,
            self.youtube_service.search_videos,
            phrase
        )
        
        logger.info(f"Found {len(video_results)} videos for phrase: {phrase}")
        return video_results
    
    async def evaluate_videos(self, phrase: str, videos: List[VideoResult]) -> List[ScoredVideo]:
        """Evaluate videos using Gemini AI."""
        logger.info(f"Evaluating {len(videos)} videos for phrase: {phrase}")
        
        if not videos:
            logger.info(f"No videos to evaluate for phrase: {phrase}")
            return []
        
        # Run AI video evaluation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        scored_videos = await loop.run_in_executor(
            None,
            self.ai_service.evaluate_videos,
            phrase,
            videos
        )
        
        # Limit to max videos per phrase
        max_videos = self.config.get('max_videos_per_phrase', 3)
        limited_videos = scored_videos[:max_videos]
        
        logger.info(f"Selected {len(limited_videos)} top-rated videos for phrase: {phrase}")
        return limited_videos
    
    async def download_videos(self, videos: List[ScoredVideo], phrase: str) -> List[str]:
        """Download videos using yt-dlp."""
        logger.info(f"Downloading {len(videos)} videos for phrase: {phrase}")
        
        if not videos:
            return []
        
        # Run video download in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        downloaded_files = await loop.run_in_executor(
            None,
            self.video_downloader.download_videos,
            videos,
            phrase
        )
        
        logger.info(f"Downloaded {len(downloaded_files)} files for phrase: {phrase}")
        return downloaded_files
    
    async def organize_files(self, job_id: str, phrase_downloads: Dict[str, List[str]]) -> str:
        """Organize downloaded files into structured folders."""
        logger.info(f"Organizing files for job: {job_id}")
        
        if not phrase_downloads:
            logger.warning(f"No files to organize for job {job_id}")
            return ""
        
        # Run file organization in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        output_path = await loop.run_in_executor(
            None,
            self.file_organizer.organize_files,
            job_id,
            phrase_downloads
        )
        
        logger.info(f"Files organized into: {output_path}")
        return output_path
    
    async def upload_to_drive(self, output_path: str, job_id: str) -> None:
        """Upload organized content to Google Drive."""
        if not self.drive_service:
            logger.warning("Google Drive service not configured, skipping upload")
            return
        
        if not output_path or not Path(output_path).exists():
            logger.warning(f"Output path does not exist: {output_path}")
            return
        
        logger.info(f"Uploading to Google Drive: {output_path}")
        
        # Run Google Drive upload in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        drive_folder_id = await loop.run_in_executor(
            None,
            self.drive_service.upload_folder,
            output_path,
            job_id
        )
        
        logger.info(f"Successfully uploaded to Google Drive (folder ID: {drive_folder_id})")
    
    async def send_notification(self, job_id: str, status: str, message: str) -> None:
        """Send email notification about job completion."""
        if not self.notification_service:
            logger.debug("Email notifications not configured, skipping notification")
            return
        
        logger.info(f"Sending notification for job {job_id}: {status} - {message}")
        
        # Get job details for notification
        job = self.processing_jobs.get(job_id)
        file_path = job.file_path if job else None
        
        # Run email sending in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self.notification_service.send_notification,
                job_id,
                status,
                message,
                file_path
            )
            logger.info(f"Email notification sent for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to send email notification for job {job_id}: {e}")