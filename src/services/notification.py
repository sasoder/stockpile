"""Email notification service for job completion alerts using Gmail API."""

import logging
import base64
import os
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.retry import retry_api_call, NetworkError

logger = logging.getLogger(__name__)

# Gmail API scope for sending emails
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class NotificationService:
    """Service for sending email notifications using Gmail API."""
    
    def __init__(self, client_id: str, client_secret: str):
        """Initialize notification service with Google OAuth credentials.
        
        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.service = None
        self.user_email = None
        
        # Create credentials from client ID and secret
        self._setup_credentials()
        
        logger.info("Initialized Gmail API notification service")
    
    def _setup_credentials(self):
        """Set up Google OAuth credentials."""
        creds = None
        
        # Check if token.json exists
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Create client config from environment variables
                client_config = {
                    "installed": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": ["http://localhost"]
                    }
                }
                
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        
        # Build the Gmail service
        self.service = build("gmail", "v1", credentials=creds)
        
        # Get user's email address
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            self.user_email = profile["emailAddress"]
            logger.info(f"Gmail API authenticated for: {self.user_email}")
        except HttpError as error:
            logger.error(f"Failed to get user profile: {error}")
            raise
    
    @retry_api_call(max_retries=3, base_delay=2.0)
    def send_notification(self, job_id: str, status: str, message: str, 
                         output_path: Optional[str] = None, 
                         drive_folder_url: Optional[str] = None) -> None:
        """Send email notification about job completion.
        
        Args:
            job_id: Job identifier
            status: Job status ('completed' or 'failed')
            message: Status message
            output_path: Local output path (if applicable)
            drive_folder_url: Google Drive folder URL (if applicable)
        """
        try:
            # Create email content
            subject = self._create_subject(job_id, status)
            body = self._create_email_body(job_id, status, message, output_path, drive_folder_url)
            
            # Send email
            self._send_email(subject, body)
            
            logger.info(f"Notification sent for job {job_id}: {status}")
            
        except HttpError as error:
            logger.error(f"Gmail API error sending notification for job {job_id}: {error}")
            raise NetworkError(f"Gmail API error: {error}")
        except Exception as e:
            logger.error(f"Failed to send notification for job {job_id}: {e}")
            raise
    
    def _create_subject(self, job_id: str, status: str) -> str:
        """Create email subject line."""
        status_text = "Completed" if status == "completed" else "Failed"
        return f"B-Roll Processing {status_text} - Job {job_id[:8]}"
    
    def _create_email_body(self, job_id: str, status: str, message: str,
                          output_path: Optional[str] = None,
                          drive_folder_url: Optional[str] = None) -> str:
        """Create email body content."""
        # Create simple text email body
        output_info = ""
        if drive_folder_url:
            output_info = f"\nGoogle Drive: {drive_folder_url}"
        elif output_path:
            output_info = f"\nLocal folder: {output_path}"
        
        body = f"""B-Roll Processing {status.title()}

Job ID: {job_id}
Status: {status.title()}
Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Message: {message}{output_info}

---
B-Roll Video Processor
"""
        
        return body
    
    def _send_email(self, subject: str, body: str) -> None:
        """Send the actual email using Gmail API.
        
        Args:
            subject: Email subject
            body: Email body (plain text)
        """
        try:
            # Create message
            message = MIMEText(body, 'plain')
            message['To'] = self.user_email
            message['From'] = self.user_email
            message['Subject'] = subject
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Send message
            send_message = self.service.users().messages().send(
                userId="me",
                body={"raw": raw_message}
            ).execute()
            
            logger.debug(f"Email sent successfully. Message ID: {send_message['id']}")
            
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise