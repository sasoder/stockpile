# B-Roll Video Processor

An automated Python application that helps video content creators find and organize relevant B-roll footage. The system processes uploaded videos by transcribing audio content, extracting contextual search phrases using AI, finding matching B-roll videos from YouTube, and organizing them into structured project folders.

## Features

- **Automated File Detection**: Monitors local folders and Google Drive for new video uploads
- **Transcription**: Uses OpenAI Whisper to convert video/audio to text
- **AI-Powered Search**: Extracts relevant search phrases from transcripts using Google Gemini
- **YouTube Integration**: Searches and downloads high-quality B-roll content using yt-dlp
- **Flexible Storage**: Supports both local directories and Google Drive for input/output
- **Smart Organization**: Creates project folders with phrase-based subfolders
- **Progress Tracking**: SQLite database tracks job status with resumable processing
- **Email Notifications**: Optional Gmail integration for job completion alerts

## Installation

### 1. Install system dependencies first
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# Windows (using Chocolatey)
choco install ffmpeg
```

### 2. Clone and setup Python environment
```bash
git clone <your-repo-url>
cd broll-video-processor

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your actual values
```

## Configuration

Edit your `.env` file with these settings:

### Required
- `GEMINI_API_KEY` - Get from [Google AI Studio](https://aistudio.google.com/)

### Input Sources (need at least one)
- `LOCAL_INPUT_FOLDER=./input` - Local folder to watch for videos
- `GOOGLE_DRIVE_INPUT_FOLDER_ID=` - Google Drive folder ID to monitor

### Output Destinations (need at least one)  
- `LOCAL_OUTPUT_FOLDER=./output` - Where to save organized B-roll locally
- `GOOGLE_DRIVE_OUTPUT_FOLDER_ID=` - Google Drive folder for output

### Google Drive (if using Drive features)
- `GOOGLE_CLIENT_ID=` - OAuth client ID from Google Cloud Console
- `GOOGLE_CLIENT_SECRET=` - OAuth client secret

### Optional Settings
- `GMAIL_USER=` / `GMAIL_PASSWORD=` - For email notifications (use App Password)
- `WHISPER_MODEL=base` - Whisper model size (tiny/base/small/medium/large)
- `GEMINI_MODEL=gemma-3-27b-it` - AI model for phrase extraction
- `MAX_CONCURRENT_JOBS=3` - How many videos to process simultaneously
- `MAX_VIDEOS_PER_PHRASE=3` - B-roll videos to download per search phrase

## Usage

### Start the daemon (monitors folders automatically)
```bash
python -m src.main
```

### Process a single file
```bash
python -m src.main process /path/to/video.mp4
```

### Check processing status
```bash
python -m src.main status
```

## How It Works

1. **File Detection**: Monitors input folders for new video files
2. **Transcription**: Extracts audio and converts to text using Whisper
3. **Phrase Extraction**: AI analyzes transcript to find B-roll search terms
4. **YouTube Search**: Finds relevant B-roll videos for each phrase
5. **Download & Organize**: Downloads videos into organized folder structure
6. **Notification**: Sends email when processing completes

## Supported Formats

**Video**: .mp4, .avi, .mov, .mkv, .wmv, .flv, .webm, .m4v  
**Audio**: .mp3, .wav, .flac, .aac, .ogg, .m4a, .wma

## Troubleshooting

**FFmpeg not found**: Make sure ffmpeg is installed and in your PATH

**Google Drive auth**: First run opens browser for OAuth - follow the prompts

**Gmail not working**: Use an App Password, not your regular Gmail password

**Import errors**: Make sure you activated the virtual environment and installed requirements.txt