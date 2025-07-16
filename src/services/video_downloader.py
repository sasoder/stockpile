"""Video download service using yt-dlp."""

import logging
import os
import re
from pathlib import Path
from typing import List, Dict, Optional
import yt_dlp

from models.video import ScoredVideo
from utils.retry import retry_download, NetworkError, TemporaryServiceError

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Service for downloading videos using yt-dlp with custom options."""
    
    def __init__(self, output_dir: str):
        """Initialize video downloader with output directory.
        
        Args:
            output_dir: Base directory for downloaded videos
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized video downloader with output dir: {self.output_dir}")
    
    @retry_download(max_retries=3, base_delay=2.0)
    def download_videos(self, videos: List[ScoredVideo], phrase: str) -> List[str]:
        """Download videos using yt-dlp with custom options.
        
        Args:
            videos: List of scored videos to download
            phrase: Search phrase for organizing downloads
            
        Returns:
            List of paths to downloaded files
        """
        if not videos:
            logger.info("No videos to download")
            return []
        
        # Create phrase-specific directory
        phrase_dir = self.output_dir / self.sanitize_filename(phrase)
        phrase_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Downloading {len(videos)} videos for phrase: '{phrase}'")
        
        downloaded_files = []
        
        for video in videos:
            try:
                downloaded_file = self._download_single_video(video, phrase_dir)
                if downloaded_file:
                    downloaded_files.append(downloaded_file)
                    logger.info(f"Downloaded: {Path(downloaded_file).name}")
                else:
                    logger.warning(f"Failed to download video: {video.video_id}")
                    
            except Exception as e:
                logger.error(f"Error downloading video {video.video_id}: {e}")
                continue
        
        logger.info(f"Successfully downloaded {len(downloaded_files)} videos for phrase: '{phrase}'")
        return downloaded_files
    
    def _download_single_video(self, video: ScoredVideo, output_dir: Path) -> Optional[str]:
        """Download a single video with yt-dlp.
        
        Args:
            video: ScoredVideo object to download
            output_dir: Directory to save the video
            
        Returns:
            Path to downloaded file or None if failed
        """
        
        # Configure yt-dlp options
        ydl_opts = {
            
            # Output template with score prefix for easy identification
            'outtmpl': str(output_dir / f'score{video.score:02d}_%(title)s.%(ext)s'),
            
            # Metadata options
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'writethumbnail': False,
            
            # Error handling
            'ignoreerrors': True,
            'no_warnings': False,
            'retries': 3,
            
            # Audio options (keep audio for B-roll)
            'extractaudio': False,
            
            # Post-processing
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            
            # Limit file size to reasonable B-roll size
            'max_filesize': 100 * 1024 * 1024,  # 100MB max
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get expected filename
                info = ydl.extract_info(video.video_result.url, download=False)
                if not info:
                    logger.error(f"Could not extract info for video: {video.video_id}")
                    return None
                
                # Check if video passes our filters
                filter_result = video_filter(info, incomplete=False)
                if filter_result:
                    logger.info(f"Video {video.video_id} filtered out: {filter_result}")
                    return None
                
                # Get expected filename
                expected_filename = ydl.prepare_filename(info)
                
                # Download the video
                ydl.download([video.video_result.url])
                
                # Check if file was actually downloaded
                if os.path.exists(expected_filename):
                    return expected_filename
                
                # Sometimes the filename changes due to post-processing
                # Look for files with similar names
                base_name = Path(expected_filename).stem
                for file_path in output_dir.glob(f"*{base_name}*"):
                    if file_path.is_file():
                        return str(file_path)
                
                logger.warning(f"Downloaded file not found: {expected_filename}")
                return None
                
        except yt_dlp.DownloadError as e:
            logger.error(f"yt-dlp download error for {video.video_id}: {e}")
            # Convert to retryable errors where appropriate
            error_msg = str(e).lower()
            if "network" in error_msg or "connection" in error_msg:
                raise NetworkError(f"Network error downloading {video.video_id}: {e}")
            elif "unavailable" in error_msg or "private" in error_msg:
                raise TemporaryServiceError(f"Video unavailable {video.video_id}: {e}")
            raise
        
        except Exception as e:
            logger.error(f"Unexpected error downloading {video.video_id}: {e}")
            raise
    
    def get_video_info(self, url: str) -> Optional[Dict]:
        """Extract video information without downloading.
        
        Args:
            url: Video URL
            
        Returns:
            Video information dictionary or None if extraction fails
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return ydl.sanitize_info(info) if info else None
        except Exception as e:
            logger.error(f"Failed to extract info for {url}: {e}")
            return None
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for filesystem compatibility.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename safe for filesystem
        """
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        filename = filename.strip('._')  # Remove leading/trailing dots and underscores
        
        # Limit length and ensure it's not empty
        filename = filename[:50] if filename else 'unnamed'
        
        return filename
    
    def cleanup_failed_downloads(self, phrase_dir: Path) -> None:
        """Clean up any partial or failed download files.
        
        Args:
            phrase_dir: Directory to clean up
        """
        try:
            # Look for common partial download patterns
            patterns = ['*.part', '*.tmp', '*.ytdl', '*.f*']
            
            for pattern in patterns:
                for file_path in phrase_dir.glob(pattern):
                    try:
                        file_path.unlink()
                        logger.debug(f"Cleaned up partial download: {file_path}")
                    except Exception as e:
                        logger.warning(f"Could not clean up {file_path}: {e}")
                        
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
    
    def get_download_stats(self, phrase_dir: Path) -> Dict[str, int]:
        """Get statistics about downloaded files in a phrase directory.
        
        Args:
            phrase_dir: Directory to analyze
            
        Returns:
            Dictionary with download statistics
        """
        if not phrase_dir.exists():
            return {'total_files': 0, 'total_size_mb': 0}
        
        total_files = 0
        total_size = 0
        
        for file_path in phrase_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.webm', '.mkv', '.avi']:
                total_files += 1
                total_size += file_path.stat().st_size
        
        return {
            'total_files': total_files,
            'total_size_mb': round(total_size / (1024 * 1024), 2)
        }