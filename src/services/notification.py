"""Email notification service for job completion alerts using Gmail API."""

import logging
import base64
import os
from email.mime.text import MIMEText
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.retry import retry_api_call, NetworkError

logger = logging.getLogger(__name__)

# API scopes for Gmail and Drive access
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
]


class NotificationService:
    """Service for sending email notifications using Gmail API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        notification_email: Optional[str] = None,
    ):
        """Initialize notification service with Google OAuth credentials.

        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.notification_email = notification_email
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
                # Create temporary credentials.json file
                credentials_config = {
                    "installed": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": ["http://localhost:8080/"],
                    }
                }

                # Write temporary credentials file
                import json

                temp_creds_file = "temp_credentials.json"
                with open(temp_creds_file, "w") as f:
                    json.dump(credentials_config, f)

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        temp_creds_file, SCOPES
                    )
                    # Ensure we get a refresh token
                    flow.run_local_server(port=8080, prompt="consent")
                    creds = flow.credentials
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_creds_file):
                        os.remove(temp_creds_file)

            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        # Build the Gmail service
        self.service = build("gmail", "v1", credentials=creds)

        # Set email address for notifications
        if self.notification_email:
            self.user_email = self.notification_email
            logger.info(f"Using configured notification email: {self.user_email}")
        else:
            logger.info(
                "No notification email configured. Notifications will not be sent."
            )

    @retry_api_call(max_retries=3, base_delay=2.0)
    def send_notification(
        self,
        status: str,
        output_path: Optional[str] = None,
        drive_folder_url: Optional[str] = None,
        processing_time: Optional[str] = None,
        input_file: Optional[str] = None,
        video_count: Optional[int] = None,
    ) -> None:
        """Send email notification about job completion.

        Args:
            status: Job status ('completed' or 'failed')
            output_path: Local output path (if applicable)
            drive_folder_url: Google Drive folder URL (if applicable)
            processing_time: Human-readable processing time (if applicable)
            input_file: Original input file that triggered the workflow (if applicable)
            video_count: Number of videos downloaded (if applicable)
        """
        try:
            # Create email content
            subject = self._create_subject(status)
            body = self._create_email_body(
                status,
                output_path,
                drive_folder_url,
                processing_time,
                input_file,
                video_count,
            )

            # Send email
            self._send_email(subject, body)

            logger.info(f"Notification sent: {status}")

        except HttpError as error:
            logger.error(f"Gmail API error sending notification: {error}")
            raise NetworkError(f"Gmail API error: {error}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            raise

    def _create_subject(self, status: str) -> str:
        """Create email subject line."""
        if status == "completed":
            return "🎬 Your B-roll videos are ready"
        else:
            return "⚠️ Issue with your B-roll processing"

    def _create_email_body(
        self,
        status: str,
        output_path: Optional[str] = None,
        drive_folder_url: Optional[str] = None,
        processing_time: Optional[str] = None,
        input_file: Optional[str] = None,
        video_count: Optional[int] = None,
    ) -> str:
        """Create email body content."""
        # Create simple text email body
        output_info = ""
        if drive_folder_url:
            output_info = f"\nGoogle Drive link: {drive_folder_url}"
        elif output_path:
            output_info = f"\nLocal folder: {output_path}"

        # Add processing time if available
        time_info = f"\n\n- Took {processing_time}" if processing_time else ""

        # Add input file information if available
        input_info = ""
        if input_file:
            from pathlib import Path

            input_filename = Path(input_file).name
            input_info = f"\n\n- Input file: {input_filename}"

        # Add video count information if available
        video_info = ""
        if video_count is not None:
            video_info = f"\n\n- Found {video_count} videos"

        if status == "completed":
            body = f"""Your B-roll videos have been processed and are ready.{input_info}{time_info}{video_info}

{output_info}
"""
        else:
            body = f"""stockpile ran into an issue while processing your B-roll videos.{input_info}{time_info}

{output_info}

You can try processing the file again or check the logs for more details.
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
            message = MIMEText(body, "plain")
            if not self.user_email:
                raise ValueError("User email is required for notifications")
            message["To"] = self.user_email
            message["From"] = self.user_email
            message["Subject"] = subject

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Send message
            if not self.service:
                raise ValueError("Gmail service not initialized")
            send_message = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )

            logger.debug(f"Email sent successfully. Message ID: {send_message['id']}")

        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise
