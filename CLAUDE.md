# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Application Overview

Stockpile is a Python-based B-roll video processor that automates the workflow of finding and organizing relevant B-roll footage for video content creators. The system monitors input sources, transcribes videos, uses AI to extract search phrases, downloads matching YouTube content, and organizes everything into structured project folders.

## Core Architecture

### Main Components
- **BRollProcessor** (`src/broll_processor.py`) - Central orchestrator that manages the entire workflow
- **Services Layer** (`src/services/`) - Modular services for each major function:
  - `transcription.py` - OpenAI Whisper integration for audio-to-text
  - `ai_service.py` - Google Gemini integration for phrase extraction
  - `youtube_service.py` - YouTube search and metadata retrieval
  - `video_downloader.py` - yt-dlp wrapper for downloading videos
  - `file_organizer.py` - Creates structured output folders
  - `drive_service.py` - Google Drive integration for input/output
  - `file_monitor.py` - Watches folders for new files using watchdog
  - `notification.py` - Email notifications via Gmail

### Data Models
- **ProcessingJob** (`src/models/job.py`) - Tracks job state and progress through pipeline
- **VideoResult** (`src/models/video.py`) - Represents downloaded videos with metadata

### Utilities
- **Database** (`src/utils/database.py`) - SQLite operations for job persistence
- **Config** (`src/utils/config.py`) - Environment variable loading and validation
- **Retry** (`src/utils/retry.py`) - Exponential backoff for API calls

## Common Commands

### Development Setup
```bash
# Install dependencies (no package.json, use requirements.txt)
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Running the Application
```bash
# Start daemon mode (monitors folders continuously)
python -m src.main

# Process a single file
python -m src.main process /path/to/video.mp4

# Check processing status
python -m src.main status
```

### Development Tools
```bash
# Code formatting
black src/

# Type checking
mypy src/

# Run tests (pytest available but no test suite currently exists)
pytest
```

## Key Configuration

The application requires `.env` configuration based on `.env.example`:
- `GEMINI_API_KEY` - Required for AI phrase extraction
- Input sources: `LOCAL_INPUT_FOLDER` or `GOOGLE_DRIVE_INPUT_FOLDER_ID`
- Output destinations: `LOCAL_OUTPUT_FOLDER` or `GOOGLE_DRIVE_OUTPUT_FOLDER_ID`
- Optional: Google OAuth credentials for Drive integration
- Optional: Email notification settings

## Processing Pipeline

1. **File Detection** - Monitor input folders for new video/audio files
2. **Transcription** - Extract audio and convert to text using Whisper
3. **AI Analysis** - Use Gemini to extract relevant B-roll search phrases
4. **YouTube Search** - Find matching videos for each phrase
5. **Download & Organization** - Download videos into phrase-based folder structure
6. **Notification** - Send completion email if configured

## Database Schema

Jobs are tracked in SQLite with states: pending, processing, completed, failed
- Each job has a unique ID, file path, status, and processing metadata
- Progress is saved at each pipeline stage for resumability

## File Organization

Output structure:
```
output/
  project_name_timestamp/
    search_phrase_1/
      score##_video_title.mp4
    search_phrase_2/
      score##_video_title.mp4
```

## Error Handling

- Services use exponential backoff retry logic for API calls
- Database transactions ensure job state consistency
- Graceful shutdown handling with SIGINT/SIGTERM
- Comprehensive logging throughout the pipeline