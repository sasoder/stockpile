"""Google Drive service for uploading organized B-roll content."""

import logging
import os
from pathlib import Path
from typing import List, Dict, Union
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from utils.retry import retry_api_call, NetworkError, TemporaryServiceError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive"
]


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
                # Create temporary credentials.json file
                credentials_config = {
                    "installed": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
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
        
        self.service = build('drive', 'v3', credentials=creds)
        logger.info("Google Drive service authenticated successfully")
    
    
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
        
        folder = self.service.files().create(body=folder_metadata, fields='id').execute() if self.service else None
        folder_id = folder.get('id') if folder else None
        
        if not folder_id:
            raise ValueError(f"Failed to create Google Drive folder: {folder_name}")
        logger.debug(f"Created Google Drive folder: {folder_name} (ID: {folder_id})")
        return folder_id
    
    
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
        ).execute() if self.service else None
        
        file_id = file.get('id') if file else None
        if not file_id:
            raise ValueError(f"Failed to upload file: {file_path.name}")
        logger.debug(f"Uploaded file: {file_path.name} (ID: {file_id})")
        return file_id
    
    def upload_file(self, file_path: str, parent_folder_id: str) -> str:
        """Upload a single file to Google Drive folder.
        
        Args:
            file_path: Path to local file to upload
            parent_folder_id: Google Drive folder ID to upload to
            
        Returns:
            Uploaded file ID
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Skip hidden files and partial downloads
        if file_path_obj.name.startswith('.') or file_path_obj.name.endswith('.part'):
            logger.debug(f"Skipping file: {file_path_obj.name}")
            return ""
        
        try:
            file_id = self._upload_file(file_path_obj, parent_folder_id)
            logger.info(f"Successfully uploaded file to Google Drive: {file_path_obj.name}")
            return file_id
            
        except Exception as e:
            logger.error(f"Failed to upload file to Google Drive: {e}")
            if "quota" in str(e).lower():
                raise TemporaryServiceError(f"Google Drive quota exceeded: {e}")
            elif "network" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            raise
    
    @retry_api_call(max_retries=3, base_delay=2.0)
    def create_project_structure(self, project_name: str, phrase_names: List[str]) -> Dict[str, Union[str, Dict[str, str]]]:
        """Create complete project folder structure in Drive.
        
        Args:
            project_name: Name of the project folder
            phrase_names: List of phrase names to create subfolders for
            
        Returns:
            Dictionary with 'project_id' and 'phrase_folders' mapping phrase -> folder_id
        """
        try:
            # Create main project folder
            project_folder_id = self._create_folder(project_name, self.output_folder_id)
            
            # Create phrase subfolders
            phrase_folders = {}
            for phrase in phrase_names:
                # Sanitize phrase name for folder
                sanitized_phrase = self._sanitize_folder_name(phrase)
                phrase_folder_id = self._create_folder(sanitized_phrase, project_folder_id)
                phrase_folders[phrase] = phrase_folder_id
            
            logger.info(f"Created Drive project structure: {project_name} with {len(phrase_folders)} phrase folders")
            return {
                'project_id': project_folder_id,
                'phrase_folders': phrase_folders
            }
            
        except Exception as e:
            logger.error(f"Failed to create Drive project structure: {e}")
            if "quota" in str(e).lower():
                raise TemporaryServiceError(f"Google Drive quota exceeded: {e}")
            elif "network" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            raise
    
    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize folder name for Drive compatibility."""
        import re
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        return sanitized[:50] if sanitized else 'unnamed'

