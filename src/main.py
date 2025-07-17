"""Main application entry point for Stockpile."""

import asyncio
import logging
import signal
import sys
from typing import Optional

from broll_processor import BRollProcessor
from utils.config import setup_logging, load_config

logger = logging.getLogger(__name__)


class BRollApp:
    """Main application class for Stockpile."""

    def __init__(self):
        self.processor: Optional[BRollProcessor] = None
        self.running = False

    async def start(self) -> None:
        """Start the Stockpile application."""
        try:
            # Setup logging
            setup_logging()
            logger.info("Starting Stockpile...")

            # Initialize processor
            config = load_config()
            self.processor = BRollProcessor(config)

            # Start processor
            self.processor.start()
            self.running = True

            # Setup signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            logger.info("Stockpile started successfully")

            # Keep the application running
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            sys.exit(1)

    def _signal_handler(self, signum, _):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False


def main():
    """Main entry point."""
    import sys

    app = BRollApp()

    try:
        # Start daemon
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
