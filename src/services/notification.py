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
                         drive_folder_url: Optional[str] = None,
                         job_details: Optional[Dict] = None) -> None:
        """Send email notification about job completion.
        
        Args:
            job_id: Job identifier
            status: Job status ('completed' or 'failed')
            message: Status message
            output_path: Local output path (if applicable)
            drive_folder_url: Google Drive folder URL (if applicable)
            job_details: Additional job details for the email
        """
        try:
            # Create email content
            subject = self._create_subject(job_id, status)
            body = self._create_email_body(
                job_id, status, message, output_path, 
                drive_folder_url, job_details
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
        """Create email subject line.
        
        Args:
            job_id: Job identifier
            status: Job status
            
        Returns:
            Email subject line
        """
        status_emoji = "✅" if status == "completed" else "❌"
        status_text = "Completed" if status == "completed" else "Failed"
        
        return f"{status_emoji} B-Roll Processing {status_text} - Job {job_id[:8]}"
    
    def _create_email_body(self, job_id: str, status: str, message: str,
                          output_path: Optional[str] = None,
                          drive_folder_url: Optional[str] = None,
                          job_details: Optional[Dict] = None) -> str:
        """Create email body content.
        
        Args:
            job_id: Job identifier
            status: Job status
            message: Status message
            output_path: Local output path
            drive_folder_url: Google Drive folder URL
            job_details: Additional job details
            
        Returns:
            Email body HTML content
        """
        # Determine primary output location for the link
        primary_output_link = None
        output_location_text = "Output not available"
        
        if drive_folder_url:
            primary_output_link = drive_folder_url
            output_location_text = f'<a href="{drive_folder_url}">📁 Open Google Drive Folder</a>'
        elif output_path:
            # For local paths, show the path but note it's local
            output_location_text = f"📁 Local folder: <code>{output_path}</code>"
        
        # Create HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: {'#28a745' if status == 'completed' else '#dc3545'};">
                    {'🎬 B-Roll Processing Complete!' if status == 'completed' else '⚠️ B-Roll Processing Failed'}
                </h2>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3>Job Details</h3>
                    <p><strong>Job ID:</strong> {job_id}</p>
                    <p><strong>Status:</strong> {status.title()}</p>
                    <p><strong>Completed:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Message:</strong> {message}</p>
                </div>
        """
        
        if status == "completed":
            html_body += f"""
                <div style="background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #28a745;">
                    <h3>📂 Your B-Roll Files Are Ready!</h3>
                    <p>{output_location_text}</p>
                </div>
            """
            
            # Add job details if available
            if job_details:
                html_body += self._add_job_details_section(job_details)
        else:
            html_body += f"""
                <div style="background-color: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #dc3545;">
                    <h3>❌ Processing Failed</h3>
                    <p>Unfortunately, your B-roll processing job encountered an error.</p>
                    <p><strong>Error:</strong> {message}</p>
                    <p>Please check your input file and try again, or contact support if the issue persists.</p>
                </div>
            """
        
        html_body += """
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d;">
                    <p>This is an automated message from your B-Roll Video Processor.</p>
                    <p>If you have any questions, please check the application logs for more details.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_body
    
    def _add_job_details_section(self, job_details: Dict) -> str:
        """Add job details section to email body.
        
        Args:
            job_details: Dictionary with job details
            
        Returns:
            HTML section with job details
        """
        details_html = """
            <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3>📊 Processing Summary</h3>
        """
        
        # Add transcript length if available
        if 'transcript_length' in job_details:
            details_html += f"<p><strong>Transcript Length:</strong> {job_details['transcript_length']} characters</p>"
        
        # Add search phrases if available
        if 'search_phrases' in job_details and job_details['search_phrases']:
            phrases_text = ", ".join(f"'{phrase}'" for phrase in job_details['search_phrases'])
            details_html += f"<p><strong>Search Phrases:</strong> {phrases_text}</p>"
        
        # Add download statistics if available
        if 'total_downloads' in job_details:
            details_html += f"<p><strong>Total Downloads:</strong> {job_details['total_downloads']} videos</p>"
        
        if 'phrases_processed' in job_details:
            details_html += f"<p><strong>Phrases Processed:</strong> {job_details['phrases_processed']}</p>"
        
        # Add processing time if available
        if 'processing_time' in job_details:
            details_html += f"<p><strong>Processing Time:</strong> {job_details['processing_time']}</p>"
        
        details_html += "</div>"
        return details_html
    
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
            
            # Add HTML body
            html_part = MimeText(body, 'html')
            msg.attach(html_part)
            
            # Connect to Gmail SMTP server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()  # Enable encryption
                server.login(self.gmail_user, self.gmail_password)
                
                # Send email
                text = msg.as_string()
                server.sendmail(self.gmail_user, [self.gmail_user], text)
            
            logger.debug("Email sent successfully via Gmail SMTP")
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error("Gmail authentication failed. Check your app password.")
            raise
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test the Gmail SMTP connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
            
            logger.info("Gmail SMTP connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"Gmail SMTP connection test failed: {e}")
            return False