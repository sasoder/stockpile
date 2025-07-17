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
    description: Optional[str] = None


@dataclass
class ScoredVideo:
    """Represents a video with AI evaluation score."""

    video_id: str
    score: int  # 1-10 rating from AI evaluator
    video_result: VideoResult
