#!/usr/bin/env python3
"""
Entry point wrapper that can be run from the project root directory.
"""

import sys
import os
from pathlib import Path


def setup_and_run():
    """Setup the environment and run the main application."""
    # Add the src directory to the Python path
    project_root = Path(__file__).parent
    src_path = project_root / "src"
    sys.path.insert(0, str(src_path))

    # Change to src directory for compatibility with relative imports
    os.chdir(src_path)

    # Import and run the main application
    from main import main

    main()


if __name__ == "__main__":
    setup_and_run()
