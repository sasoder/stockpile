"""YouTube search service using yt-dlp for finding B-roll videos."""

import logging
import yt_dlp
from typing import List, Dict, Optional

from ..models.video import VideoResult
from ..utils.retry import retry_api_call, NetworkError, TemporaryServiceError

logger = logging.getLogger(__name__)


class YouTubeService:
    """Service for searching YouTube videos using yt-dlp."""
    
    def __init__(self, max_results: int = 20):
        """Initialize YouTube search service."""
        self.max_results = max_results
        
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
        }
    
    @retry_api_call(max_retries=3, base_delay=2.0)
    def search_videos(self, search_phrase: str) -> List[VideoResult]:
        """Search YouTube for videos matching the search phrase."""
        if not search_phrase.strip():
            return []
        
        logger.info(f"Searching YouTube for: '{search_phrase}'")
        
        try:
            search_query = f"ytsearch{self.max_results}:{search_phrase}"
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)
                
                if not search_results or 'entries' not in search_results:
                    return []
                
                video_results = []
                for entry in search_results['entries']:
                    if entry is None:
                        continue
                    
                    video_result = self._parse_video_entry(entry)
                    if video_result:
                        video_results.append(video_result)
                
                logger.info(f"Found {len(video_results)} videos for '{search_phrase}'")
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
            video_id = entry.get('id')
            if not video_id:
                return None
            
            return VideoResult(
                video_id=video_id,
                title=entry.get('title', 'Unknown Title'),
                url=f"https://www.youtube.com/watch?v={video_id}",
                duration=entry.get('duration', 0) or 0,
                description=entry.get('description', '')
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse video entry: {e}")
            return None