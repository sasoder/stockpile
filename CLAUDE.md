# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

B-Roll Video Processor is a daemon that automatically processes video files to find and organize B-roll footage. It monitors folders for new videos, transcribes them, extracts search phrases using AI, finds matching YouTube videos, and organizes them with email notifications.

## Development Commands

### Setup
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Running the Daemon
```bash
# Start daemon (monitors folders continuously)
cd src && python main.py

# Check job status
cd src && python main.py status
```

## Core Architecture

### Processing Pipeline
1. **File Detection** (`services/file_monitor.py`) - Monitors local/Google Drive folders
2. **Transcription** (`services/transcription.py`) - Whisper audio-to-text
3. **AI Phrase Extraction** (`services/ai_service.py`) - B-RollExtractor v6 prompt
4. **YouTube Search** (`services/youtube_service.py`) - yt-dlp video search
5. **Video Evaluation** (`services/ai_service.py`) - AI scoring (1-10 scale)
6. **Download & Organization** (`services/video_downloader.py`, `services/file_organizer.py`)
7. **Notifications** (`services/notification.py`) - Gmail alerts

### Key Components
- **BRollProcessor** (`src/broll_processor.py`) - Main orchestrator
- **Job Management** (`src/models/job.py`) - SQLite-based state tracking
- **Configuration** (`src/utils/config.py`) - Environment variable validation
- **Retry Logic** (`src/utils/retry.py`) - API and network error handling

## Critical Implementation Details

### B-RollExtractor v6 Prompt
Located in `src/services/ai_service.py:45-70`. This is the exact prompt from the original n8n workflow:
- Extracts 5-10 visual search phrases
- Focuses on concrete, filmable concepts
- Avoids abstract ideas and copyrighted content
- Returns JSON array of 1-4 word phrases

### File Monitoring
- **Local**: Uses `watchdog` library for real-time monitoring
- **Google Drive**: Polls every 30 seconds using Drive API
- **Supported formats**: Video (.mp4, .avi, .mov, .mkv, .wmv, .flv, .webm, .m4v) and audio (.mp3, .wav, .flac, .aac, .ogg, .m4a, .wma)

### Configuration Requirements
Environment variables in `.env`:
- **Required**: `GEMINI_API_KEY`
- **Input**: `LOCAL_INPUT_FOLDER` OR `GOOGLE_DRIVE_INPUT_FOLDER_ID`
- **Output**: `LOCAL_OUTPUT_FOLDER` OR `GOOGLE_DRIVE_OUTPUT_FOLDER_ID`
- **Google Drive**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- **Notifications**: Uses same Google credentials as Drive API

## Known Issues

### Critical Bug - Email Notifications
**Location**: `src/broll_processor.py` in `_handle_new_file()` and `process_video()`
**Issue**: Job failure notifications are never sent because exceptions propagate up without triggering `send_notification()`
**Fix needed**: Add try/catch in `_handle_new_file()` to catch exceptions and send failure notifications

### Dependencies
- **External**: Requires ffmpeg system installation
- **API Keys**: Gemini API for AI processing
- **OAuth**: Google Drive requires initial browser authentication

## Recent Cleanup

### Removed Bloat
- Single file processing functionality
- Complex HTML email notifications (now simple text)
- Unused database cleanup function
- Overly complex status display methods
- Unused retry imports

## Database Schema
SQLite database tracks job state with these key fields:
- `job_id`, `status` (pending/processing/completed/failed)
- `file_path`, `source` (local/google_drive)
- `transcript`, `search_phrases`, `error_message`
- `created_at`, `completed_at`

## Development Notes
- All services use `@retry_api_call` decorator for network resilience
- Temporary files auto-cleaned after processing
- Job state persists across application restarts