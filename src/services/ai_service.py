"""AI service for phrase extraction and video evaluation using Google GenAI."""

import json
import logging
from typing import List
from google.genai import Client
from google.genai import types

from utils.retry import retry_api_call, APIRateLimitError, NetworkError
from models.video import VideoResult, ScoredVideo

logger = logging.getLogger(__name__)


def strip_markdown_code_blocks(text: str) -> str:
    """Strip markdown code blocks from AI response text.
    
    Args:
        text: Raw text that may contain markdown code blocks
        
    Returns:
        Cleaned text with markdown code blocks removed
    """
    text = text.strip()
    if text.startswith('```json'):
        text = text[7:]  # Remove ```json
    elif text.startswith('```'):
        text = text[3:]  # Remove ```
    if text.endswith('```'):
        text = text[:-3]  # Remove ```
    return text.strip()


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
        prompt = f"""You are B-RollExtractor v6.

GOAL
Turn the transcript into stock-footage search phrases an editor can paste into Pexels, YouTube, etc.

OUTPUT
Return one JSON string array and nothing else.

Example: ["Berlin Wall falling", "vintage CRT monitor close-up", "Hitler with Stalin", "Mao era parade"]

RULES
• ≥10 phrases.
• 2–6 words each.
• Must name a tangible scene, person, object or event (no pure ideas).
• Use simple connectors ("with", "in", "during") to relate entities.
• No duplicates or name-spamming combos ("Hitler Stalin Mao").
• No markdown, no extra keys, no surrounding text.

GOOD
"1930s Kremlin meeting"
"Stalin official portrait"
"Hitler with Stalin"

BAD
"policy shift"         (abstract)
"Power dynamics"        (abstract)
"Hitler Stalin Mao"     (unclear)
"massive power"         (no concrete noun)

TRANSCRIPT ↓
<<<
{transcript}
>>>"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.85,
                )
            )
            
            # Parse JSON response
            try:
                # Strip markdown code blocks if present
                if not response.text:
                    logger.error("AI response is empty")
                    return []
                response_text = strip_markdown_code_blocks(response.text)
                
                phrases = json.loads(response_text)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract phrases from text
                logger.warning("Failed to parse JSON response, attempting to extract phrases from text")
                logger.info(f"Raw AI response: {response.text}")
                import re
                # Look for quoted phrases or lines that look like phrases
                text = response.text
                if not text:
                    logger.error("AI response is empty")
                    return []
                phrases = re.findall(r'"([^"]+)"', text)
                if not phrases:
                    # Fallback: split by lines and filter
                    lines = text.strip().split('\n')
                    phrases = [line.strip(' -•*') for line in lines if line.strip() and len(line.strip()) < 50]
            
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
            f"URL: {video.url}\n"
            "---"
            for video in video_results
        ])
        
        evaluator_prompt = f"""You are B-Roll Evaluator. Your goal is to select the most visually relevant YouTube videos for a given search phrase.

You will be given a search phrase and a list of YouTube search results including their titles and descriptions.

SEARCH PHRASE:
"{search_phrase}"

YOUTUBE RESULTS:
---
{results_text}
---

TASK:
1. Analyze the title and description of each video.
2. Compare them against the search phrase.
3. Choose the videos that are most likely to contain generic, high-quality B-roll footage matching the phrase.
4. Prioritize cinematic shots, stock footage, documentary clips. Avoid vlogs, talk shows, tutorials, or videos with prominent branding.
5. Rate each video from 1-10 based on B-roll potential.

OUTPUT:
Return a JSON array of objects with video_id and score for videos scoring 6 or higher, ordered by score (highest first).
Format: [{{"video_id": "abc123", "score": 9}}, {{"video_id": "def456", "score": 7}}]
Return only the JSON array, nothing else."""
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=evaluator_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Low temperature for consistent evaluation
                )
            )
            
            # Parse JSON response
            try:
                # Strip markdown code blocks if present
                if not response.text:
                    logger.error("AI response is empty")
                    return []
                response_text = strip_markdown_code_blocks(response.text)
                
                scored_results = json.loads(response_text)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse video evaluation response as JSON: {response.text}")
                logger.warning("Attempting to extract video IDs and scores from text response")
                import re
                # Try to extract video_id and score pairs from text
                text = response.text
                if not text:
                    logger.error("AI response is empty")
                    return []
                matches = re.findall(r'"video_id":\s*"([^"]+)".*?"score":\s*(\d+)', text)
                scored_results = [{"video_id": vid_id, "score": int(score)} for vid_id, score in matches if int(score) >= 6]
                if not scored_results:
                    logger.error("Could not extract any valid video evaluations from response")
                    return []
            
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
    
