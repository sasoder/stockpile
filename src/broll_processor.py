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
            await self.upload_to_drive(output_path)
        
        # Step 6: Send notification
        await self.send_notification(job.job_id, "completed", "Job completed successfully")
    
    # Placeholder methods for pipeline steps (to be implemented in subsequent tasks)
    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio content using Whisper."""
        # TODO: Implement in Task 4
        logger.info(f"Transcribing audio from {file_path}")
        await asyncio.sleep(1)  # Simulate processing
        return "Sample transcript for development"
    
    async def extract_search_phrases(self, transcript: str) -> List[str]:
        """Extract relevant search phrases using Gemini AI."""
        # TODO: Implement in Task 5
        logger.info("Extracting search phrases from transcript")
        await asyncio.sleep(1)  # Simulate processing
        return ["sample phrase 1", "sample phrase 2", "sample phrase 3"]
    
    async def search_youtube_videos(self, phrase: str) -> List[VideoResult]:
        """Search YouTube for videos matching the phrase."""
        # TODO: Implement in Task 6
        logger.info(f"Searching YouTube for: {phrase}")
        await asyncio.sleep(1)  # Simulate processing
        return []
    
    async def evaluate_videos(self, phrase: str, videos: List[VideoResult]) -> List[ScoredVideo]:
        """Evaluate videos using Gemini AI."""
        # TODO: Implement in Task 6
        logger.info(f"Evaluating videos for phrase: {phrase}")
        await asyncio.sleep(1)  # Simulate processing
        return []
    
    async def download_videos(self, videos: List[ScoredVideo], phrase: str) -> List[str]:
        """Download videos using yt-dlp."""
        # TODO: Implement in Task 7
        logger.info(f"Downloading videos for phrase: {phrase}")
        await asyncio.sleep(1)  # Simulate processing
        return []
    
    async def organize_files(self, job_id: str, phrase_downloads: Dict[str, List[str]]) -> str:
        """Organize downloaded files into structured folders."""
        # TODO: Implement in Task 8
        logger.info(f"Organizing files for job: {job_id}")
        await asyncio.sleep(1)  # Simulate processing
        return f"output/{job_id}"
    
    async def upload_to_drive(self, output_path: str) -> None:
        """Upload organized content to Google Drive."""
        # TODO: Implement in Task 8
        logger.info(f"Uploading to Google Drive: {output_path}")
        await asyncio.sleep(1)  # Simulate processing
    
    async def send_notification(self, job_id: str, status: str, message: str) -> None:
        """Send email notification about job completion."""
        # TODO: Implement in Task 9
        logger.info(f"Sending notification for job {job_id}: {status} - {message}")
        await asyncio.sleep(0.1)  # Simulate processing