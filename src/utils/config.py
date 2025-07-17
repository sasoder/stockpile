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
        'local_input_folder': os.getenv('LOCAL_INPUT_FOLDER', '../input'),
        'google_drive_input_folder_id': os.getenv('GOOGLE_DRIVE_INPUT_FOLDER_ID'),
        
        # Output destinations (at least one required)
        'local_output_folder': os.getenv('LOCAL_OUTPUT_FOLDER', '../output'),
        'google_drive_output_folder_id': os.getenv('GOOGLE_DRIVE_OUTPUT_FOLDER_ID'),
        
        
        # Model configurations
        'whisper_model': os.getenv('WHISPER_MODEL', 'base'),
        'gemini_model': os.getenv('GEMINI_MODEL', 'gemma-3-27b-it'),
        
        # Google Drive OAuth
        'google_client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'google_client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
        
        # Processing settings
        'max_videos_per_phrase': int(os.getenv('MAX_VIDEOS_PER_PHRASE', '3')),
        'max_video_duration_seconds': int(os.getenv('MAX_VIDEO_DURATION_SECONDS', '600')),
        
        # Database
        'database_path': os.getenv('DATABASE_PATH', 'stockpile_jobs.db'),
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
    has_drive_input = bool(config.get('google_drive_input_folder_id'))
    
    if not (has_local_input or has_drive_input):
        errors.append("At least one input source required: LOCAL_INPUT_FOLDER or GOOGLE_DRIVE_INPUT_FOLDER_ID")
    
    # Check output destinations (at least one required)
    has_local_output = bool(config.get('local_output_folder'))
    has_drive_output = bool(config.get('google_drive_output_folder_id'))
    
    if not (has_local_output or has_drive_output):
        errors.append("At least one output destination required: LOCAL_OUTPUT_FOLDER or GOOGLE_DRIVE_OUTPUT_FOLDER_ID")
    
    # Validate local paths exist
    if has_local_input:
        input_path = Path(config['local_input_folder'])
        try:
            input_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create local input folder: {e}")
    
    if has_local_output:
        output_path = Path(config['local_output_folder'])
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create local output folder: {e}")
    
    # Validate Google Drive credentials if using Google Drive
    if has_drive_output or has_drive_input:
        if not config.get('google_client_id') or not config.get('google_client_secret'):
            errors.append("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required for Google Drive integration")
    
    
    # YouTube search is handled by yt-dlp directly, no API key validation needed
    
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