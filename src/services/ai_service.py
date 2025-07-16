"""AI service for phrase extraction and video evaluation using Google GenAI."""

import json
import logging
from typing import List, Dict, Optional
from google.genai import Client
from google.genai import types

from ..utils.retry import retry_api_call, APIRateLimitError, NetworkError
from ..models.video import VideoResult, ScoredVideo

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered phrase extraction and video evaluation using Gemini."""
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-001"):
        """Initialize Google GenAI client.
        
        Args:
            api_key: Google GenAI API key
            model_name: Gemini model to use
        """
        self.api_key = api_key
        self.model_name = model_name
        self.client = Client(api_key=api_key)
        
        logger.info(f"Initialized AI service with model: {model_name}")
    
    @retry_api_call(max_retries=5, base_delay=2.0)
    def extract_search_phrases(self, transcript: str) -> List[str]:
        """Extract B-roll search phrases from transcript using Gemini.
        
        Args:
            transcript: Transcribed text content
            
        Returns:
            List of search phrases for B-roll footage
        """
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript provided for phrase extraction")
            return []
        
        # B-Roll Extractor v6 prompt (from original n8n workflow)
        prompt = f"""
You are B-Roll Extractor v6. Your goal is to extract relevant search phrases for finding B-roll footage.

Analyze this transcript and extract 5-10 specific, visual search phrases that would help find relevant B-roll footage:

TRANSCRIPT:
{transcript}

REQUIREMENTS:
1. Focus on visual, concrete concepts that can be filmed
2. Avoid abstract ideas, emotions, or concepts that can't be visualized
3. Prioritize nouns and noun phrases that represent physical objects, places, or activities
4. Keep phrases 1-4 words long for effective search
5. Remove duplicates and very similar phrases
6. Choose phrases that would yield generic, high-quality stock footage
7. Avoid brand names, specific people, or copyrighted content

EXAMPLES OF GOOD PHRASES:
- "city skyline", "coffee shop", "morning commute"
- "ocean waves", "mountain landscape", "busy street"
- "typing keyboard", "handshake", "sunset"

Return only a JSON array of strings, nothing else.
Format: ["phrase1", "phrase2", "phrase3"]
"""
        
        try:
            logger.info("Extracting search phrases from transcript")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=300,
                    response_mime_type='application/json'
                )
            )
            
            # Parse JSON response
            phrases = json.loads(response.text)
            
            # Validate and clean phrases
            if not isinstance(phrases, list):
                logger.error("AI response is not a list")
                return []
            
            # Filter and clean phrases
            cleaned_phrases = []
            for phrase in phrases:
                if isinstance(phrase, str) and phrase.strip():
                    clean_phrase = phrase.strip().lower()
                    if len(clean_phrase) > 0 and clean_phrase not in cleaned_phrases:
                        cleaned_phrases.append(clean_phrase)
            
            # Limit to 10 phrases
            final_phrases = cleaned_phrases[:10]
            
            logger.info(f"Extracted {len(final_phrases)} search phrases: {final_phrases}")
            return final_phrases
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
            return []
        
        except Exception as e:
            logger.error(f"Phrase extraction failed: {e}")
            # Convert specific errors to retryable errors
            if "rate limit" in str(e).lower():
                raise APIRateLimitError(f"Rate limit hit: {e}")
            elif "network" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            raise
    
    @retry_api_call(max_retries=3, base_delay=1.0)
    def evaluate_videos(self, search_phrase: str, video_results: List[VideoResult]) -> List[ScoredVideo]:
        """Evaluate YouTube videos for B-roll suitability using Gemini.
        
        Args:
            search_phrase: The search phrase used to find videos
            video_results: List of video search results
            
        Returns:
            List of scored videos (score >= 6 only)
        """
        if not video_results:
            logger.info(f"No videos to evaluate for phrase: {search_phrase}")
            return []
        
        # Format video results for AI evaluation
        results_text = "\n".join([
            f"ID: {video.video_id}\n"
            f"Title: {video.title}\n"
            f"Description: {video.description[:200] if video.description else 'N/A'}...\n"
            f"Duration: {video.duration}s\n"
            f"Channel: {video.channel_title or 'Unknown'}\n"
            "---"
            for video in video_results
        ])
        
        evaluator_prompt = f"""
You are B-Roll Evaluator. Your goal is to select the most visually relevant YouTube videos for a given search phrase.

You will be given a search phrase and a list of YouTube search results including their titles and descriptions.

SEARCH PHRASE: "{search_phrase}"

YOUTUBE RESULTS:
{results_text}

TASK:
1. Analyze the title and description of each video
2. Compare them against the search phrase for relevance
3. Choose videos that are most likely to contain generic, high-quality B-roll footage matching the phrase
4. Prioritize:
   - Cinematic shots and professional footage
   - Stock footage and documentary clips
   - Generic, reusable content
5. Avoid:
   - Vlogs and talking head videos
   - Talk shows and interviews
   - Tutorials and how-to videos
   - Videos with prominent branding or logos
   - Music videos or entertainment content
6. Rate each video from 1-10 based on B-roll potential

SCORING CRITERIA:
- 9-10: Perfect B-roll footage, cinematic quality
- 7-8: Good B-roll potential, professional quality
- 6: Acceptable B-roll, some usable footage
- 1-5: Poor B-roll potential (exclude from results)

OUTPUT:
Return a JSON array of objects with video_id and score for videos scoring 6 or higher, ordered by score (highest first).

Format: [{{"video_id": "abc123", "score": 9}}, {{"video_id": "def456", "score": 7}}]

Return only the JSON array, nothing else.
"""
        
        try:
            logger.info(f"Evaluating {len(video_results)} videos for phrase: {search_phrase}")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=evaluator_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Low temperature for consistent evaluation
                    max_output_tokens=500,
                    response_mime_type='application/json'
                )
            )
            
            # Parse JSON response
            scored_results = json.loads(response.text)
            
            # Validate response format
            if not isinstance(scored_results, list):
                logger.error("AI evaluation response is not a list")
                return []
            
            # Create ScoredVideo objects
            scored_videos = []
            video_lookup = {v.video_id: v for v in video_results}
            
            for item in scored_results:
                if not isinstance(item, dict) or 'video_id' not in item or 'score' not in item:
                    logger.warning(f"Invalid scored video format: {item}")
                    continue
                
                video_id = item['video_id']
                score = item['score']
                
                # Validate score
                if not isinstance(score, (int, float)) or score < 6 or score > 10:
                    logger.warning(f"Invalid score {score} for video {video_id}")
                    continue
                
                # Find corresponding video result
                if video_id not in video_lookup:
                    logger.warning(f"Video ID {video_id} not found in original results")
                    continue
                
                scored_video = ScoredVideo(
                    video_id=video_id,
                    score=int(score),
                    video_result=video_lookup[video_id]
                )
                scored_videos.append(scored_video)
            
            # Sort by score (highest first)
            scored_videos.sort(key=lambda x: x.score, reverse=True)
            
            logger.info(f"Evaluated videos for '{search_phrase}': {len(scored_videos)} videos scored >= 6")
            return scored_videos
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse video evaluation response as JSON: {e}")
            logger.debug(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
            return []
        
        except Exception as e:
            logger.error(f"Video evaluation failed for phrase '{search_phrase}': {e}")
            # Convert specific errors to retryable errors
            if "rate limit" in str(e).lower():
                raise APIRateLimitError(f"Rate limit hit: {e}")
            elif "network" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"Network error: {e}")
            raise
    
