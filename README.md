# 🎞️ stockpile

Upload video to Google Drive → Get Gmail notification 5 minutes later → Click link to b-roll organized by topic. Uses AI to search and score relevant footage. Works locally or syncs with Google Drive.

## ⚡ Quick Start (Local)

**Requirements:** Python 3.8+, FFmpeg, Google Gemini API key

```bash
# clone and install
git clone https://github.com/yourusername/stockpile.git
cd stockpile
# set up virtual environment
python -m venv .venv
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt

# configure
cp .env.example .env
# add your GEMINI_API_KEY to .env

# run locally
python stockpile.py
```

Drop videos in `input/`, get organized b-roll in `output/`.

## ☁️ Google Drive Integration (recommended)

For cloud workflow with automated Drive uploads:

**1. Create OAuth Client:**

- Create a Google Cloud project
- Enable Google Drive API and Gmail API
- Go to [Google Cloud Console OAuth Clients](https://console.cloud.google.com/auth/clients) to create a new client.
- Save the client ID and secret to your `.env` file.
- When you start the script for the first time, it will prompt you to authorize your client.

**2. Configure Drive folders:**

```bash
# Add to .env
GOOGLE_DRIVE_INPUT_FOLDER_ID=your_input_folder_id
GOOGLE_DRIVE_OUTPUT_FOLDER_ID=your_output_folder_id
GOOGLE_CLIENT_ID=your_oauth_client_id
GOOGLE_CLIENT_SECRET=your_oauth_client_secret
NOTIFICATION_EMAIL=your@email.com
```

Now drop videos in your Google Drive input folder, get organized b-roll uploaded to your output folder with email notification when it's complete.

## How it works

1. Drop your video in input folder (local or Google Drive)
2. AI transcribes and extracts key topics/visuals from your clip
3. YouTube search finds high-quality b-roll for each topic
4. AI evaluates each video for b-roll quality and visual relevance
5. Get a drive link to organized folders with scored videos ready to edit

```
📁 output/
  └── your_project_20250718/
      ├── 🏭 industrial_revolution_factory/
      │   ├── score08_vintage_factory_footage.mp4
      │   └── score09_steam_engine_documentary.mp4
      ├── ⚙️ steel_production_process/
      │   └── score07_molten_steel_pouring.mp4
      └── 👷 workers_assembly_line/
          └── score08_ford_assembly_line_1920s.mp4
```

## 🖥️ VPS Deployment

For cloud deployment, use the same OAuth setup as above:

```bash
# Deploy to your VPS
git clone https://github.com/yourusername/stockpile.git
cd stockpile
pip install -r requirements.txt

# Configure same as Google Drive integration
cp .env.example .env
# Add your API keys and OAuth credentials
```

## ⚙️ Configuration

- `GEMINI_API_KEY` - get from Google AI Studio (required)
- `MAX_VIDEOS_PER_PHRASE=3` - videos downloaded per topic
- `MAX_VIDEO_DURATION_SECONDS=900` - skip videos longer than 15min
- **Local:** uses `LOCAL_INPUT_FOLDER` and `LOCAL_OUTPUT_FOLDER` folders
- **Google Drive:** set `GOOGLE_DRIVE_INPUT_FOLDER_ID` and `GOOGLE_DRIVE_OUTPUT_FOLDER_ID`
- **Notifications:** add `NOTIFICATION_EMAIL` for completion alerts

Questions? Check `src/broll_processor.log` or [open an issue](https://github.com/yourusername/stockpile/issues).
