# B-Roll Video Processor

An automated Python application that helps video content creators find and organize relevant B-roll footage. The system processes uploaded videos by transcribing audio content, extracting contextual search phrases using AI, finding matching B-roll videos from YouTube, and organizing them into structured project folders.

## Features

- **Automated Transcription**: Uses OpenAI Whisper to convert video/audio to text
- **AI-Powered Search**: Leverages Gemini AI to extract relevant search phrases from transcripts
- **YouTube Integration**: Searches and downloads high-quality B-roll content using yt-dlp
- **Flexible Storage**: Supports both local directories and Google Drive for input/output
- **Smart Organization**: Creates project folders with phrase-based subfolders for easy access
- **Progress Tracking**: SQLite database tracks job status with resumable processing
- **Email Notifications**: Gmail integration for job completion alerts
- **File Monitoring**: Automatic processing when new files are detected

## Installation

1. **Clone the repository**
   ```bash
   git clone git@github.com:sasoder/stockpile.git
   cd broll-video-processor
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install system dependencies**
   ```bash
   # macOS
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt update && sudo apt install ffmpeg
   
   # Windows (using Chocolatey)
   choco install ffmpeg
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

## Configuration

### Required Environment Variables

- `GEMINI_API_KEY` - Google Gemini AI API key for phrase extraction
- At least one input source:
  - `LOCAL_INPUT_FOLDER` - Local directory to monitor for videos
  - `GOOGLE_DRIVE_FOLDER_ID` - Google Drive folder ID to monitor
- At least one output destination:
  - `LOCAL_OUTPUT_FOLDER` - Local directory for organized B-roll
  - `GOOGLE_DRIVE_CREDENTIALS_PATH` - Path to Google Drive credentials JSON

### Optional Configuration

- `GMAIL_USER` / `GMAIL_PASSWORD` - For email notifications (use Gmail App Password)
- `WHISPER_MODEL` - Whisper model size (tiny, base, small, medium, large, turbo)
- `GEMINI_MODEL` - Gemini model to use (default: gemma-3-27b-it)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - Required only if using Google Drive
- `MAX_CONCURRENT_JOBS` - Number of simultaneous processing jobs (default: 3)
- `MAX_VIDEOS_PER_PHRASE` - Maximum B-roll videos per search phrase (default: 3)
- `VIDEO_DURATION_LIMIT` - Maximum video length in seconds (default: 600)

## Usage

### Start the Processor Daemon

```bash
python -m src.main start
```

### Process a Single File

```bash
python -m src.main process /path/to/video.mp4
```

### Check Status

```bash
python -m src.main status
```

### Command Line Options

```bash
# Start with custom config
python -m src.main start --config /path/to/config.env

# Process file from Google Drive
python -m src.main process video.mp4 --source google_drive
```

## Project Structure

```
src/
├── main.py                 # Application entry point
├── broll_processor.py      # Main processor class
├── models/
│   ├── job.py             # ProcessingJob and JobStatus models
│   └── video.py           # VideoResult and ScoredVideo models
├── utils/
│   ├── config.py          # Configuration loading and validation
│   ├── database.py        # Database utilities
│   └── retry.py           # Retry logic and backoff
└── services/              # Service implementations (to be added)
```

## Development Status

This is the initial implementation with core infrastructure in place. The following components are implemented:

✅ **Core Infrastructure**
- Project structure and configuration
- Database schema and job management
- Main processor class with pipeline orchestration
- Command-line interface and application entry point

🚧 **In Progress**
- Audio transcription service (Whisper integration)
- AI phrase extraction service (Gemini integration)
- YouTube search and video evaluation
- Video downloading with yt-dlp
- File organization and Google Drive upload
- Email notification system
- File monitoring service

## API Keys Setup

### Google Gemini AI (Required)
1. Visit [Google AI Studio](https://aistudio.google.com/)
2. Create an API key
3. Add to `.env` as `GEMINI_API_KEY`

### Google Drive (Optional - for cloud storage)
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Google Drive API
3. Create OAuth 2.0 credentials (Desktop application type)
4. Download credentials JSON file
5. Set path in `.env` as `GOOGLE_DRIVE_CREDENTIALS_PATH`
6. Add Client ID and Secret to `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

### Gmail Notifications (Optional)
1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password (not your regular password)
3. Add your email to `.env` as `GMAIL_USER`
4. Add the App Password to `.env` as `GMAIL_PASSWORD`

**Note**: YouTube video search and downloading is handled directly by yt-dlp and requires no API keys.

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]