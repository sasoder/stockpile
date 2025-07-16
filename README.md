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
   git clone <repository-url>
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

- `GMAIL_USER` / `GMAIL_PASSWORD` - For email notifications
- `YOUTUBE_API_KEY` - For YouTube video search
- `WHISPER_MODEL` - Whisper model size (tiny, base, small, medium, large, turbo)
- `GEMINI_MODEL` - Gemini model to use (default: gemini-2.0-flash-001)

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

### Google Gemini AI
1. Visit [Google AI Studio](https://aistudio.google.com/)
2. Create an API key
3. Add to `.env` as `GEMINI_API_KEY`

### YouTube Data API
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Enable YouTube Data API v3
3. Create credentials (API key)
4. Add to `.env` as `YOUTUBE_API_KEY`

### Google Drive (Optional)
1. Create a project in Google Cloud Console
2. Enable Google Drive API
3. Create OAuth 2.0 credentials
4. Download credentials JSON file
5. Set path in `.env` as `GOOGLE_DRIVE_CREDENTIALS_PATH`

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]