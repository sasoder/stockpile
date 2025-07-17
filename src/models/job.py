"""Job and status models for Stockpile."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
import json


class JobStatus(Enum):
    """Status enumeration for processing jobs."""
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    EXTRACTING_PHRASES = "extracting_phrases"
    SEARCHING_YOUTUBE = "searching_youtube"
    DOWNLOADING = "downloading"
    ORGANIZING = "organizing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingJob:
    """Represents a processing job with all its state."""
    
    job_id: str
    file_path: str
    source: str  # 'local' or 'google_drive'
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    transcript: Optional[str] = None
    search_phrases: Optional[List[str]] = None
    downloaded_files: Optional[Dict[str, List[str]]] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    drive_folder_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert job to dictionary for database storage."""
        return {
            'job_id': self.job_id,
            'file_path': self.file_path,
            'source': self.source,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'transcript': self.transcript,
            'search_phrases': json.dumps(self.search_phrases) if self.search_phrases else None,
            'downloaded_files': json.dumps(self.downloaded_files) if self.downloaded_files else None,
            'output_path': self.output_path,
            'error_message': self.error_message,
            'drive_folder_url': self.drive_folder_url
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ProcessingJob':
        """Create job from dictionary loaded from database."""
        return cls(
            job_id=data['job_id'],
            file_path=data['file_path'],
            source=data['source'],
            status=JobStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            transcript=data.get('transcript'),
            search_phrases=json.loads(data['search_phrases']) if data.get('search_phrases') else None,
            downloaded_files=json.loads(data['downloaded_files']) if data.get('downloaded_files') else None,
            output_path=data.get('output_path'),
            error_message=data.get('error_message'),
            drive_folder_url=data.get('drive_folder_url')
        )
    
    def update_status(self, new_status: JobStatus, error_message: Optional[str] = None) -> None:
        """Update job status and timestamp."""
        self.status = new_status
        self.updated_at = datetime.now()
        if error_message:
            self.error_message = error_message