"""Database utilities for job tracking and progress persistence."""

import sqlite3
import logging
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..models.job import ProcessingJob, JobStatus

logger = logging.getLogger(__name__)


def init_database(db_path: str) -> None:
    """Initialize SQLite database with required tables."""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Create jobs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                transcript TEXT,
                search_phrases TEXT,
                downloaded_files TEXT,
                output_path TEXT,
                error_message TEXT,
                drive_folder_url TEXT
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)')
        
        conn.commit()
        logger.info(f"Database initialized at {db_path}")


@contextmanager
def get_db_connection(db_path: str):
    """Context manager for database connections."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    try:
        yield conn
    finally:
        conn.close()


def save_job_progress(job: ProcessingJob, db_path: str) -> None:
    """Save job progress to database."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        job_data = job.to_dict()
        
        # Use INSERT OR REPLACE to handle both new and updated jobs
        cursor.execute('''
            INSERT OR REPLACE INTO jobs (
                job_id, file_path, source, status, created_at, updated_at,
                transcript, search_phrases, downloaded_files, output_path, error_message, drive_folder_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_data['job_id'],
            job_data['file_path'],
            job_data['source'],
            job_data['status'],
            job_data['created_at'],
            job_data['updated_at'],
            job_data['transcript'],
            job_data['search_phrases'],
            job_data['downloaded_files'],
            job_data['output_path'],
            job_data['error_message'],
            job_data['drive_folder_url']
        ))
        
        conn.commit()
        logger.debug(f"Saved job progress: {job.job_id} - {job.status.value}")


def load_job(job_id: str, db_path: str) -> Optional[ProcessingJob]:
    """Load a specific job from database."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
        row = cursor.fetchone()
        
        if row:
            return ProcessingJob.from_dict(dict(row))
        return None


def load_incomplete_jobs(db_path: str) -> List[ProcessingJob]:
    """Load all incomplete jobs from database for resumption."""
    incomplete_statuses = [
        JobStatus.QUEUED.value,
        JobStatus.TRANSCRIBING.value,
        JobStatus.EXTRACTING_PHRASES.value,
        JobStatus.SEARCHING_YOUTUBE.value,
        JobStatus.DOWNLOADING.value,
        JobStatus.ORGANIZING.value,
        JobStatus.UPLOADING.value
    ]
    
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(incomplete_statuses))
        cursor.execute(
            f'SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at',
            incomplete_statuses
        )
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append(ProcessingJob.from_dict(dict(row)))
        
        logger.info(f"Loaded {len(jobs)} incomplete jobs for resumption")
        return jobs


def get_job_statistics(db_path: str) -> Dict[str, int]:
    """Get statistics about jobs in the database."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Count jobs by status
        cursor.execute('''
            SELECT status, COUNT(*) as count 
            FROM jobs 
            GROUP BY status
        ''')
        
        stats = {}
        for row in cursor.fetchall():
            stats[row['status']] = row['count']
        
        # Total jobs
        cursor.execute('SELECT COUNT(*) as total FROM jobs')
        stats['total'] = cursor.fetchone()['total']
        
        return stats


def get_recent_jobs(db_path: str, limit: int = 10) -> List[ProcessingJob]:
    """Get most recent jobs for status display."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM jobs 
            ORDER BY updated_at DESC 
            LIMIT ?
        ''', (limit,))
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append(ProcessingJob.from_dict(dict(row)))
        
        return jobs


