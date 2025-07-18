"""Video download service using yt-dlp."""

import logging
import re
from pathlib import Path
from typing import List, Dict, Optional
import yt_dlp

from models.video import ScoredVideo
from utils.retry import retry_download, NetworkError, TemporaryServiceError
from utils.config import load_config

logger = logging.getLogger(__name__)

logging.getLogger("yt_dlp").setLevel(logging.CRITICAL)
logging.getLogger("yt_dlp.extractor").setLevel(logging.CRITICAL)
logging.getLogger("yt_dlp.downloader").setLevel(logging.CRITICAL)
logging.getLogger("yt_dlp.postprocessor").setLevel(logging.CRITICAL)


def video_filter(info: Dict) -> Optional[str]:
    """Filter videos based on duration and other criteria.

    Args:
        info: Video information dictionary from yt-dlp

    Returns:
        String describing why video was filtered, or None if it passes
    """
    config = load_config()
    max_duration = config.get("max_video_duration_seconds", 600)
    max_size = config.get("max_video_size_mb", 100) * 1024 * 1024
    # Check duration
    duration = info.get("duration")
    if duration is not None and duration > max_duration:
        return f"Duration {duration}s exceeds maximum {max_duration}s"

    size = info.get("filesize")
    if size is not None and size > max_size:
        return f"Size {size} exceeds maximum {max_size} bytes"

    return None


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

        logger.info(
            f"Download completed: {len(downloaded_files)} videos for phrase: '{phrase}'"
        )
        return downloaded_files

    def download_videos_to_folder(
        self,
        videos: List[ScoredVideo],
        phrase: str,
        target_folder: str,
        drive_service=None,
        drive_folder_id: str | None = None,
    ) -> List[str]:
        """Download videos directly to a specific target folder with optional Drive upload.

        Args:
            videos: List of scored videos to download
            phrase: Search phrase (for logging)
            target_folder: Exact target folder path
            drive_service: Optional DriveService instance for immediate upload
            drive_folder_id: Drive folder ID to upload to

        Returns:
            List of paths to downloaded files
        """
        if not videos:
            logger.info(f"No videos to download for phrase: {phrase}")
            return []

        target_path = Path(target_folder)
        target_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Downloading {len(videos)} videos for phrase '{phrase}' to: {target_path}"
        )

        downloaded_files = []
        for video in videos:
            try:
                downloaded_file = self._download_single_video(video, target_path)
                if downloaded_file:
                    downloaded_files.append(downloaded_file)
                    logger.info(f"Downloaded: {Path(downloaded_file).name}")

                    # Upload to Drive if service and folder ID are provided
                    if drive_service and drive_folder_id:
                        try:
                            drive_service.upload_file(downloaded_file, drive_folder_id)
                            logger.info(
                                f"Uploaded to Drive: {Path(downloaded_file).name}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Drive upload failed for {Path(downloaded_file).name}: {e}"
                            )
                else:
                    logger.warning(f"Failed to download video: {video.video_id}")
            except Exception as e:
                logger.error(f"Error downloading video {video.video_id}: {e}")
                continue

        logger.info(
            f"Successfully downloaded {len(downloaded_files)} videos for phrase: '{phrase}'"
        )
        return downloaded_files

    def _download_single_video(
        self, video: ScoredVideo, output_dir: Path
    ) -> Optional[str]:
        """Download a single video with yt-dlp.

        Args:
            video: ScoredVideo object to download
            output_dir: Directory to save the video

        Returns:
            Path to downloaded file or None if failed
        """

        # Get config for file size limit
        config = load_config()
        max_size = config.get("max_video_size_mb", 100) * 1024 * 1024

        # Configure yt-dlp options
        ydl_opts = {
            # Output template with score prefix for easy identification
            "outtmpl": str(output_dir / f"score{video.score:02d}_%(title)s.%(ext)s"),
            # Metadata options
            "writeinfojson": False,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "writethumbnail": False,
            # Error handling
            "ignoreerrors": True,
            "no_warnings": True,  # Suppress warnings
            "retries": 3,
            # Audio options (keep audio for B-roll)
            "extractaudio": False,
            # Post-processing with ffmpeg suppression
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            ],
            # Suppress all ffmpeg output completely
            "postprocessor_args": {
                "FFmpeg": ["-v", "quiet", "-nostats", "-loglevel", "error"],
                "Merger+ffmpeg": ["-v", "quiet", "-nostats", "-loglevel", "error"],
                "VideoConvertor+ffmpeg": [
                    "-v",
                    "quiet",
                    "-nostats",
                    "-loglevel",
                    "error",
                ],
                "VideoRemuxer+ffmpeg": [
                    "-v",
                    "quiet",
                    "-nostats",
                    "-loglevel",
                    "error",
                ],
                "ExtractAudio+ffmpeg": [
                    "-v",
                    "quiet",
                    "-nostats",
                    "-loglevel",
                    "error",
                ],
            },
            "max_filesize": max_size,  # Use configured max size
            # Logging options - complete suppression
            "quiet": True,  # Suppress most output
            "no_progress": True,  # Disable progress bar
        }

        try:
            # First, extract video info without downloading to pre-filter
            info_opts = {
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(info_opts) as info_ydl:
                info = info_ydl.extract_info(video.video_result.url, download=False)
                if not info:
                    logger.error(f"Could not extract info for video: {video.video_id}")
                    return None

                # Pre-filter video before starting download
                filter_result = video_filter(info)
                if filter_result:
                    logger.info(f"Video {video.video_id} filtered out: {filter_result}")
                    return None

                # Get expected filename using the actual download template
                expected_filename = str(
                    output_dir
                    / f'score{video.score:02d}_{info.get("title", "unknown")}.{info.get("ext", "mp4")}'
                )
                logger.info(
                    f"Pre-filtering passed, starting download: {Path(expected_filename).name}"
                )

            # Get list of files before download
            files_before = set(output_dir.glob("*"))

            # Now download the video using the full options
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video.video_result.url])

                # Find newly created files with the score prefix
                files_after = set(output_dir.glob("*"))
                new_files = files_after - files_before

                score_prefix = f"score{video.score:02d}_"
                for file_path in new_files:
                    if file_path.is_file() and file_path.name.startswith(score_prefix):
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
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                result = ydl.sanitize_info(info) if info else None
                return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"Failed to extract info for {url}: {e}")
            return None

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        filename = re.sub(r"\s+", "_", filename)
        filename = filename.strip("._")
        filename = filename[:50] if filename else "unnamed"
        return filename

    def cleanup_failed_downloads(self, phrase_dir: Path) -> None:
        """Clean up any partial or failed download files.

        Args:
            phrase_dir: Directory to clean up
        """
        try:
            patterns = ["*.part", "*.tmp", "*.ytdl", "*.f*"]

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
            return {"total_files": 0, "total_size_mb": 0}

        total_files = 0
        total_size = 0

        for file_path in phrase_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in [
                ".mp4",
                ".webm",
                ".mkv",
                ".avi",
            ]:
                total_files += 1
                total_size += file_path.stat().st_size

        return {
            "total_files": int(total_files),
            "total_size_mb": int(round(total_size / (1024 * 1024), 2)),
        }
