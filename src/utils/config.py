"""Configuration loading and validation for B-Roll Video Processor."""

import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def load_config() -> Dict:
    """Load configuration from environment variables."""
    config = {
        # Required API keys
        'gemini_api_key': os.getenv('GEMINI_API_KEY'),
        
        # Input sources (at least one required)
        'local_input_folder': os.getenv('LOCAL_INPUT_FOLDER'),
        'google_drive_folder_id': os.getenv('GOOGLE_DRIVE_FOLDER_ID'),
        
        # Output destinations (at least one required)
        'local_output_folder': os.getenv('LOCAL_OUTPUT_FOLDER'),
        'google_drive_credentials_path': os.getenv('GOOGLE_DRIVE_CREDENTIALS_PATH'),
        
        # Email notifications
        'gmail_user': os.getenv('GMAIL_USER'),
        'gmail_password': os.getenv('GMAIL_PASSWORD'),  # App password
        
        # Model configurations
        'whisper_model': os.getenv('WHISPER_MODEL', 'base'),
        'gemini_model': os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-001'),
        
        # Google Drive OAuth
        'google_client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'google_client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
        
        # YouTube API
        'youtube_api_key': os.getenv('YOUTUBE_API_KEY'),
        
        # Processing settings
        'max_concurrent_jobs': int(os.getenv('MAX_CONCURRENT_JOBS', '3')),
        'max_videos_per_phrase': int(os.getenv('MAX_VIDEOS_PER_PHRASE', '3')),
        'video_duration_limit': int(os.getenv('VIDEO_DURATION_LIMIT', '600')),  # 10 minutes
        
        # Database
        'database_path': os.getenv('DATABASE_PATH', 'broll_jobs.db'),
    }
    
    return config


def validate_config(config: Dict) -> List[str]:
    """Validate configuration and return list of errors."""
    errors = []
    
    # Check required API key
    if not config.get('gemini_api_key'):
        errors.append("GEMINI_API_KEY is required")
    
    # Check input sources (at least one required)
    has_local_input = bool(config.get('local_input_folder'))
    has_drive_input = bool(config.get('google_drive_folder_id'))
    
    if not (has_local_input or has_drive_input):
        errors.append("At least one input source required: LOCAL_INPUT_FOLDER or GOOGLE_DRIVE_FOLDER_ID")
    
    # Check output destinations (at least one required)
    has_local_output = bool(config.get('local_output_folder'))
    has_drive_output = bool(config.get('google_drive_credentials_path'))
    
    if not (has_local_output or has_drive_output):
        errors.append("At least one output destination required: LOCAL_OUTPUT_FOLDER or GOOGLE_DRIVE_CREDENTIALS_PATH")
    
    # Validate local paths exist
    if has_local_input:
        input_path = Path(config['local_input_folder'])
        if not input_path.exists():
            errors.append(f"Local input folder does not exist: {input_path}")
    
    if has_local_output:
        output_path = Path(config['local_output_folder'])
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create local output folder: {e}")
    
    # Validate Google Drive credentials
    if has_drive_output:
        creds_path = Path(config['google_drive_credentials_path'])
        if not creds_path.exists():
            errors.append(f"Google Drive credentials file not found: {creds_path}")
    
    # Validate Gmail configuration if provided
    gmail_user = config.get('gmail_user')
    gmail_password = config.get('gmail_password')
    if gmail_user and not gmail_password:
        errors.append("GMAIL_PASSWORD required when GMAIL_USER is provided")
    
    # Validate YouTube API key if Google Drive is used
    if has_drive_input and not config.get('youtube_api_key'):
        errors.append("YOUTUBE_API_KEY required for video search functionality")
    
    return errors


def setup_logging(log_level: str = "INFO") -> None:
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('broll_processor.log')
        ]
    )


def get_supported_video_formats() -> List[str]:
    """Return list of supported video file extensions."""
    return ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v']


def get_supported_audio_formats() -> List[str]:
    """Return list of supported audio file extensions."""
    return ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma']