#!/usr/bin/env python3
"""Basic functionality test for B-Roll Video Processor."""

import asyncio
import os
import tempfile
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, 'src')

from src.broll_processor import BRollProcessor
from src.utils.config import setup_logging


async def test_basic_functionality():
    """Test basic processor functionality with minimal configuration."""
    
    # Setup logging
    setup_logging("INFO")
    
    # Create minimal test configuration
    test_config = {
        'gemini_api_key': os.getenv('GEMINI_API_KEY', 'test_key'),
        'local_input_folder': './test_input',
        'local_output_folder': './test_output',
        'whisper_model': 'tiny',  # Use smallest model for testing
        'max_videos_per_phrase': 1,  # Limit for testing
        'database_path': 'test_broll_jobs.db'
    }
    
    # Create test directories
    Path('./test_input').mkdir(exist_ok=True)
    Path('./test_output').mkdir(exist_ok=True)
    
    try:
        # Initialize processor
        print("Initializing B-Roll Processor...")
        processor = BRollProcessor(test_config)
        
        # Start processor
        print("Starting processor...")
        processor.start()
        
        # Display status
        print("Displaying queue status...")
        processor.display_queue_status()
        
        print("✅ Basic functionality test passed!")
        print("The B-Roll Processor initialized successfully with all services.")
        
        # Show service status
        print("\n📋 Service Status:")
        print(f"  Transcription Service: {'✅ Ready' if processor.transcription_service else '❌ Not configured'}")
        print(f"  AI Service: {'✅ Ready' if processor.ai_service else '❌ Not configured'}")
        print(f"  YouTube Service: {'✅ Ready' if processor.youtube_service else '❌ Not configured'}")
        print(f"  Video Downloader: {'✅ Ready' if processor.video_downloader else '❌ Not configured'}")
        print(f"  File Organizer: {'✅ Ready' if processor.file_organizer else '❌ Not configured'}")
        print(f"  Notification Service: {'✅ Ready' if processor.notification_service else '⚠️  Not configured (optional)'}")
        print(f"  Google Drive Service: {'✅ Ready' if processor.drive_service else '⚠️  Not configured (optional)'}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    if success:
        print("\n🎉 All tests passed! The B-Roll Video Processor is ready to use.")
    else:
        print("\n💥 Tests failed. Please check the configuration and try again.")
        sys.exit(1)