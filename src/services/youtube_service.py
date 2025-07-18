"""YouTube search service using yt-dlp for finding B-roll videos."""

import logging
import yt_dlp
from typing import List, Dict, Optional

from models.video import VideoResult
from utils.retry import retry_api_call, NetworkError, TemporaryServiceError
from utils.config import load_config

logger = logging.getLogger(__name__)

# Configure yt-dlp logging to be silent
logging.getLogger("yt_dlp").setLevel(logging.CRITICAL)
logging.getLogger("yt_dlp.extractor").setLevel(logging.CRITICAL)
logging.getLogger("yt_dlp.downloader").setLevel(logging.CRITICAL)


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


class YouTubeService:
    """Service for searching YouTube videos using yt-dlp."""

    def __init__(self, max_results: int = 20):
        """Initialize YouTube search service."""
        self.max_results = max_results

        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "ignoreerrors": True,
        }

    @retry_api_call(max_retries=3, base_delay=2.0)
    def search_videos(self, search_phrase: str) -> List[VideoResult]:
        """Search YouTube for videos matching the search phrase."""
        if not search_phrase.strip():
            return []

        logger.info(f"Searching YouTube for: '{search_phrase}'")

        try:
            search_query = f"ytsearch{self.max_results}:{search_phrase} footage"

            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)

                if not search_results or "entries" not in search_results:
                    return []

                video_results = []
                filtered_count = 0
                for entry in search_results["entries"]:
                    if entry is None:
                        continue

                    # Filter video before parsing
                    filter_result = video_filter(entry)
                    if filter_result:
                        filtered_count += 1
                        logger.debug(
                            f"Video {entry.get('id', 'unknown')} filtered: {filter_result}"
                        )
                        continue

                    video_result = self._parse_video_entry(entry)
                    if video_result:
                        video_results.append(video_result)

                if filtered_count > 0:
                    logger.info(
                        f"Filtered out {filtered_count} videos that didn't meet criteria"
                    )
                return video_results

        except Exception as e:
            logger.error(f"YouTube search failed for '{search_phrase}': {e}")
            if "network" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            elif "unavailable" in str(e).lower():
                raise TemporaryServiceError(f"YouTube unavailable: {e}")
            raise

    def _parse_video_entry(self, entry: Dict) -> Optional[VideoResult]:
        """Parse a yt-dlp video entry into a VideoResult object."""
        try:
            video_id = entry.get("id")
            if not video_id:
                return None

            return VideoResult(
                video_id=video_id,
                title=entry.get("title", "Unknown Title"),
                url=f"https://www.youtube.com/watch?v={video_id}",
                duration=entry.get("duration", 0) or 0,
                description=entry.get("description", ""),
            )

        except Exception as e:
            logger.warning(f"Failed to parse video entry: {e}")
            return None
