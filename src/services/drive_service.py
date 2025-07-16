"""Google Drive service for uploading organized B-roll content."""

import logging
import os
from pathlib import Path
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from utils.retry import retry_api_call, NetworkError, TemporaryServiceError

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']


class DriveService:
    """Service for uploading files to Google Drive."""
    
    def __init__(self, client_id: str, client_secret: str, output_folder_id: str):
        """Initialize Google Drive service.
        
        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret  
            output_folder_id: Google Drive folder ID to upload to
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.output_folder_id = output_folder_id
        self.service = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Google Drive API."""
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
                # Create flow from client config
                flow = Flow.from_client_config(
                    {
                        "web": {
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token"
                        }
                    },
                    SCOPES
                )
                flow.redirect_uri = 'http://localhost:8080/callback'
                creds = flow.run_local_server(port=8080)
            
            # Save credentials for next run
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        logger.info("Google Drive service authenticated successfully")
    
    @retry_api_call(max_retries=3, base_delay=2.0)
    def upload_folder(self, local_folder_path: str, job_id: str) -> str:
        """Upload a local folder to Google Drive.
        
        Args:
            local_folder_path: Path to local folder to upload
            job_id: Job identifier for folder naming
            
        Returns:
            URL to the Google Drive folder
        """
        local_path = Path(local_folder_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local folder not found: {local_folder_path}")
        
        logger.info(f"Uploading folder to Google Drive: {local_folder_path}")
        
        try:
            # Create project folder in Drive
            folder_name = f"broll_project_{job_id[:8]}"
            project_folder_id = self._create_folder(folder_name, self.output_folder_id)
            
            # Upload all files and subfolders
            self._upload_directory_contents(local_path, project_folder_id)
            
            # Return shareable URL
            folder_url = f"https://drive.google.com/drive/folders/{project_folder_id}"
            logger.info(f"Successfully uploaded folder to Google Drive: {folder_name}")
            return folder_url
            
        except Exception as e:
            logger.error(f"Failed to upload folder to Google Drive: {e}")
            if "quota" in str(e).lower():
                raise TemporaryServiceError(f"Google Drive quota exceeded: {e}")
            elif "network" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            raise
    
    def _create_folder(self, folder_name: str, parent_folder_id: str) -> str:
        """Create a folder in Google Drive.
        
        Args:
            folder_name: Name of folder to create
            parent_folder_id: Parent folder ID
            
        Returns:
            Created folder ID
        """
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        
        folder = self.service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
        
        logger.debug(f"Created Google Drive folder: {folder_name} (ID: {folder_id})")
        return folder_id
    
    def _upload_directory_contents(self, local_dir: Path, drive_folder_id: str) -> None:
        """Recursively upload directory contents to Google Drive.
        
        Args:
            local_dir: Local directory path
            drive_folder_id: Google Drive folder ID to upload to
        """
        for item in local_dir.iterdir():
            if item.is_file():
                self._upload_file(item, drive_folder_id)
            elif item.is_dir():
                # Create subfolder and upload its contents
                subfolder_id = self._create_folder(item.name, drive_folder_id)
                self._upload_directory_contents(item, subfolder_id)
    
    def _upload_file(self, file_path: Path, parent_folder_id: str) -> str:
        """Upload a single file to Google Drive.
        
        Args:
            file_path: Path to local file
            parent_folder_id: Google Drive folder ID to upload to
            
        Returns:
            Uploaded file ID
        """
        file_metadata = {
            'name': file_path.name,
            'parents': [parent_folder_id]
        }
        
        media = MediaFileUpload(str(file_path), resumable=True)
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')
        logger.debug(f"Uploaded file: {file_path.name} (ID: {file_id})")
        return file_id