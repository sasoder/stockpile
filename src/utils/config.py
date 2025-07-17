"""Configuration loading and validation for Stockpile."""

import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv
from rich.logging import RichHandler
from rich.console import Console

# Get the project root directory (parent of src)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Load environment variables from .env file in project root
load_dotenv(PROJECT_ROOT / '.env')


def load_config() -> Dict:
    """Load configuration from environment variables."""
    # Helper function to resolve paths relative to project root
    def resolve_path(path: str, default_relative: str) -> str:
        if not path:
            return str(PROJECT_ROOT / default_relative)
        if Path(path).is_absolute():
            return path
        return str(PROJECT_ROOT / path)
    
    config = {
        # Required API keys
        'gemini_api_key': os.getenv('GEMINI_API_KEY'),
        
        # Input sources (at least one required)
        'local_input_folder': resolve_path(os.getenv('LOCAL_INPUT_FOLDER'), 'input'),
        'google_drive_input_folder_id': os.getenv('GOOGLE_DRIVE_INPUT_FOLDER_ID'),
        
        # Output destinations (at least one required)
        'local_output_folder': resolve_path(os.getenv('LOCAL_OUTPUT_FOLDER'), 'output'),
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
        
        # Database (always relative to src directory)
        'database_path': str(PROJECT_ROOT / 'src' / os.getenv('DATABASE_PATH', 'stockpile_jobs.db')),
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
    """Set up logging configuration with Rich for beautiful terminal output."""
    # Clear any existing handlers
    logging.root.handlers.clear()
    
    # Rich handler for beautiful console output
    rich_handler = RichHandler(
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=True,
        markup=False  # Disable markup to avoid conflicts
    )
    
    # File handler for plain text logging (always in src directory)
    log_file = PROJECT_ROOT / 'src' / 'broll_processor.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=[rich_handler, file_handler],
        format="%(message)s"
    )
    
    # Suppress noisy third-party loggers
    noisy_loggers = [
        'httpx',
        'google_genai',
        'google_genai.models',
        'googleapiclient.discovery_cache',
        'google_auth_oauthlib.flow',
        'urllib3.connectionpool',
        'requests.packages.urllib3.connectionpool'
    ]
    
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_supported_video_formats() -> List[str]:
    """Return list of supported video file extensions."""
    return ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v']


def get_supported_audio_formats() -> List[str]:
    """Return list of supported audio file extensions."""
    return ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma']