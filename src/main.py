"""Main application entry point for B-Roll Video Processor."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .broll_processor import BRollProcessor
from .utils.config import setup_logging, load_config
from .utils.database import get_job_statistics

logger = logging.getLogger(__name__)


class BRollApp:
    """Main application class for B-Roll Video Processor."""
    
    def __init__(self):
        self.processor: Optional[BRollProcessor] = None
        self.running = False
    
    async def start(self, config_path: Optional[str] = None) -> None:
        """Start the B-Roll Processor application."""
        try:
            # Setup logging
            setup_logging()
            logger.info("Starting B-Roll Video Processor...")
            
            # Initialize processor
            config = load_config() if not config_path else self._load_custom_config(config_path)
            self.processor = BRollProcessor(config)
            
            # Start processor
            self.processor.start()
            self.running = True
            
            # Setup signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            logger.info("B-Roll Video Processor started successfully")
            
            # Keep the application running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            sys.exit(1)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def _load_custom_config(self, config_path: str) -> dict:
        """Load configuration from custom path."""
        # TODO: Implement custom config loading if needed
        return load_config()
    
    async def process_single_file(self, file_path: str, source: str = "local") -> None:
        """Process a single file and exit."""
        setup_logging()
        
        try:
            processor = BRollProcessor()
            processor.start()
            
            logger.info(f"Processing single file: {file_path}")
            job_id = await processor.process_video(file_path, source)
            logger.info(f"File processed successfully. Job ID: {job_id}")
            
        except Exception as e:
            logger.error(f"Failed to process file: {e}")
            sys.exit(1)
    
    def show_status(self) -> None:
        """Show current processor status and exit."""
        setup_logging(log_level="WARNING")  # Reduce log noise for status display
        
        try:
            processor = BRollProcessor()
            processor.display_queue_status()
            
            # Show database statistics
            stats = get_job_statistics(processor.db_path)
            print(f"\nDatabase Statistics:")
            print(f"  Total jobs: {stats.get('total', 0)}")
            for status, count in stats.items():
                if status != 'total':
                    print(f"  {status.title()}: {count}")
            
        except Exception as e:
            logger.error(f"Failed to show status: {e}")
            sys.exit(1)


def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(description="B-Roll Video Processor")
    parser.add_argument(
        "--config", 
        help="Path to custom configuration file"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command (default)
    start_parser = subparsers.add_parser("start", help="Start the processor daemon")
    start_parser.add_argument("--config", help="Path to custom configuration file")
    
    # Process command
    process_parser = subparsers.add_parser("process", help="Process a single file")
    process_parser.add_argument("file_path", help="Path to video file to process")
    process_parser.add_argument("--source", default="local", choices=["local", "google_drive"],
                               help="Source type of the file")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show current status")
    
    args = parser.parse_args()
    
    app = BRollApp()
    
    try:
        if args.command == "process":
            # Process single file
            asyncio.run(app.process_single_file(args.file_path, args.source))
        elif args.command == "status":
            # Show status
            app.show_status()
        else:
            # Default: start daemon
            asyncio.run(app.start(args.config))
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()