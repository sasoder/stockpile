"""Video-related data models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class VideoResult:
    """Represents a YouTube video search result."""
    
    video_id: str
    title: str
    url: str
    duration: int  # in seconds
    relevance_score: float
    thumbnail_url: str
    description: Optional[str] = None
    channel_title: Optional[str] = None
    view_count: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'video_id': self.video_id,
            'title': self.title,
            'url': self.url,
            'duration': self.duration,
            'relevance_score': self.relevance_score,
            'thumbnail_url': self.thumbnail_url,
            'description': self.description,
            'channel_title': self.channel_title,
            'view_count': self.view_count
        }


@dataclass
class ScoredVideo:
    """Represents a video with AI evaluation score."""
    
    video_id: str
    score: int  # 1-10 rating from AI evaluator
    video_result: VideoResult
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'video_id': self.video_id,
            'score': self.score,
            'video_result': self.video_result.to_dict()
        }