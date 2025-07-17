"""File monitoring service for watching input sources."""

import logging
import asyncio
import time
from pathlib import Path
from typing import Set, Optional, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os

from utils.config import get_supported_video_formats, get_supported_audio_formats
from utils.retry import retry_api_call, NetworkError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive"
]


class VideoFileHandler(FileSystemEventHandler):
    """Handler for local file system events."""
    
    def __init__(self, callback: Callable[[str, str], None]):
        """Initialize handler with callback function.
        
        Args:
            callback: Function to call when new video file is detected
        """
        self.callback = callback
        self.supported_formats = get_supported_video_formats() + get_supported_audio_formats()
        self.processed_files: Set[str] = set()
    
    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return
        
        file_path = Path(str(event.src_path))
        if self._is_supported_file(file_path) and str(file_path) not in self.processed_files:
            # Wait a bit to ensure file is fully written
            time.sleep(2)
            if file_path.exists():
                self.processed_files.add(str(file_path))
                logger.info(f"New video file detected: {file_path}")
                self.callback(str(file_path), "local")
    
    def _is_supported_file(self, file_path: Path) -> bool:
        """Check if file is a supported video/audio format."""
        return file_path.suffix.lower() in self.supported_formats


class FileMonitor:
    """Service for monitoring input sources for new video files."""
    
    def __init__(self, config: dict, file_callback: Callable[[str, str], None]):
        """Initialize file monitor.
        
        Args:
            config: Configuration dictionary
            file_callback: Function to call when new file is detected (file_path, source)
        """
        self.config = config
        self.file_callback = file_callback
        self.observer = None
        self.drive_service = None
        self.known_drive_files: Set[str] = set()
        self.running = False
        
        # Initialize Google Drive service if needed
        if config.get('google_drive_input_folder_id'):
            self._init_drive_service()
    
    def _init_drive_service(self):
        """Initialize Google Drive service for monitoring."""
        client_id = self.config.get('google_client_id')
        client_secret = self.config.get('google_client_secret')
        
        if not client_id or not client_secret:
            logger.warning("Google Drive input monitoring disabled: missing client credentials")
            return
        
        try:
            creds = None
            token_path = 'token.json'
            
            # Load existing token
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
            # If no valid credentials, get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    # Create temporary credentials.json file
                    credentials_config = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost:8080/"]
                        }
                    }
                    
                    # Write temporary credentials file
                    import json
                    temp_creds_file = "temp_credentials.json"
                    with open(temp_creds_file, 'w') as f:
                        json.dump(credentials_config, f)
                    
                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(temp_creds_file, SCOPES)
                        # Ensure we get a refresh token
                        flow.run_local_server(port=8080, prompt='consent')
                        creds = flow.credentials
                    finally:
                        # Clean up temp file
                        if os.path.exists(temp_creds_file):
                            os.remove(temp_creds_file)
                
                # Save credentials for next run
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            
            self.drive_service = build('drive', 'v3', credentials=creds)
            logger.info("Google Drive monitoring service initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive service: {e}")
            self.drive_service = None
    
    def start_monitoring(self):
        """Start monitoring all configured input sources."""
        self.running = True
        logger.info("Starting file monitoring...")
        
        # Start local folder monitoring
        local_input_folder = self.config.get('local_input_folder')
        if local_input_folder:
            self._start_local_monitoring(local_input_folder)
        
        # Start Google Drive monitoring
        if self.drive_service and self.config.get('google_drive_input_folder_id'):
            asyncio.create_task(self._monitor_drive_folder())
        
        logger.info("File monitoring started")
    
    def stop_monitoring(self):
        """Stop all monitoring."""
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        logger.info("File monitoring stopped")
    
    def _start_local_monitoring(self, folder_path: str):
        """Start monitoring local folder for new files."""
        folder = Path(folder_path)
        if not folder.exists():
            logger.warning(f"Local input folder does not exist: {folder_path}")
            return
        
        # Process existing files first
        self._process_existing_files(folder)
        
        # Start watching for new files
        event_handler = VideoFileHandler(self.file_callback)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(folder), recursive=False)
        self.observer.start()
        
        logger.info(f"Started monitoring local folder: {folder_path}")
    
    def _process_existing_files(self, folder: Path):
        """Process any existing files in the folder."""
        supported_formats = get_supported_video_formats() + get_supported_audio_formats()
        
        for file_path in folder.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                logger.info(f"Found existing video file: {file_path}")
                self.file_callback(str(file_path), "local")
    
    async def _monitor_drive_folder(self):
        """Monitor Google Drive folder for new files."""
        folder_id = self.config.get('google_drive_input_folder_id')
        logger.info(f"Started monitoring Google Drive folder: {folder_id}")
        
        # Get initial file list
        await self._update_known_drive_files(folder_id)
        
        # Poll for changes every 30 seconds
        while self.running:
            try:
                await asyncio.sleep(30)
                await self._check_for_new_drive_files(folder_id)
            except Exception as e:
                logger.error(f"Error monitoring Google Drive: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    @retry_api_call(max_retries=3, base_delay=2.0)
    async def _update_known_drive_files(self, folder_id: str):
        """Update the set of known files in Google Drive folder."""
        try:
            results = self.drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, modifiedTime)"
            ).execute() if self.drive_service else {'files': []}
            
            files = results.get('files', [])
            self.known_drive_files = {file['id'] for file in files if self._is_video_file(file)}
            logger.debug(f"Found {len(self.known_drive_files)} existing files in Google Drive")
            
        except Exception as e:
            logger.error(f"Failed to list Google Drive files: {e}")
            if "network" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            raise
    
    async def _check_for_new_drive_files(self, folder_id: str):
        """Check for new files in Google Drive folder."""
        try:
            results = self.drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="modifiedTime desc"
            ).execute() if self.drive_service else {'files': []}
            
            files = results.get('files', [])
            
            for file in files:
                if self._is_video_file(file) and file['id'] not in self.known_drive_files:
                    # New video file found
                    self.known_drive_files.add(file['id'])
                    
                    # Download file temporarily for processing
                    temp_path = await self._download_drive_file(file)
                    if temp_path:
                        logger.info(f"New Google Drive video file: {file['name']}")
                        self.file_callback(temp_path, "google_drive")
            
        except Exception as e:
            logger.error(f"Error checking for new Google Drive files: {e}")
    
    def _is_video_file(self, file_info: dict) -> bool:
        """Check if Google Drive file is a video file."""
        mime_type = file_info.get('mimeType', '')
        name = file_info.get('name', '')
        
        # Check by MIME type
        if mime_type.startswith('video/') or mime_type.startswith('audio/'):
            return True
        
        # Check by file extension
        supported_formats = get_supported_video_formats() + get_supported_audio_formats()
        return any(name.lower().endswith(ext) for ext in supported_formats)
    
    async def _download_drive_file(self, file_info: dict) -> Optional[str]:
        """Download a file from Google Drive to temporary location.
        
        Args:
            file_info: File information from Google Drive API
            
        Returns:
            Path to downloaded temporary file or None if failed
        """
        try:
            import tempfile
            
            # Create temporary file
            temp_dir = Path(tempfile.gettempdir()) / "broll_processor"
            temp_dir.mkdir(exist_ok=True)
            
            file_name = file_info['name']
            temp_path = temp_dir / file_name
            
            # Download file
            request = self.drive_service.files().get_media(fileId=file_info['id'])
            
            with open(temp_path, 'wb') as f:
                f.write(request.execute())
            
            logger.info(f"Downloaded Google Drive file to: {temp_path}")
            return str(temp_path)
            
        except Exception as e:
            logger.error(f"Failed to download Google Drive file {file_info['name']}: {e}")
            return None