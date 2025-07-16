"""Email notification service for job completion alerts."""

import logging
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from typing import Optional, Dict
from datetime import datetime
from pathlib import Path

from ..utils.retry import retry_api_call, NetworkError

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending email notifications about job completion."""
    
    def __init__(self, gmail_user: str, gmail_password: str):
        """Initialize notification service with Gmail credentials.
        
        Args:
            gmail_user: Gmail email address
            gmail_password: Gmail app password (not regular password)
        """
        self.gmail_user = gmail_user
        self.gmail_password = gmail_password
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        
        logger.info(f"Initialized notification service for: {gmail_user}")
    
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
            body = self._create_email_body(
                job_id, status, message, output_path, 
                drive_folder_url
            )
            
            # Send email
            self._send_email(subject, body)
            
            logger.info(f"Notification sent for job {job_id}: {status}")
            
        except Exception as e:
            logger.error(f"Failed to send notification for job {job_id}: {e}")
            # Convert network errors to retryable errors
            if "network" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"Network error sending notification: {e}")
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
        """Send the actual email using SMTP.
        
        Args:
            subject: Email subject
            body: Email body (HTML)
        """
        try:
            # Create message
            msg = MimeMultipart('alternative')
            msg['From'] = self.gmail_user
            msg['To'] = self.gmail_user  # Send to self
            msg['Subject'] = subject
            
            # Add plain text body
            text_part = MimeText(body, 'plain')
            msg.attach(text_part)
            
            # Connect to Gmail SMTP server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()  # Enable encryption
                server.login(self.gmail_user, self.gmail_password)
                
                # Send email
                text = msg.as_string()
                server.sendmail(self.gmail_user, [self.gmail_user], text)
            
            logger.debug("Email sent successfully via Gmail SMTP")
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
    
