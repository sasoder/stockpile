"""File organization service for structuring downloads."""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FileOrganizer:
    """Service for organizing downloaded B-roll files into structured project folders."""

    def __init__(self, base_output_dir: str):
        """Initialize file organizer with base output directory.

        Args:
            base_output_dir: Base directory for organized files
        """
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized file organizer with base dir: {self.base_output_dir}")

    def organize_files(
        self,
        job_id: str,
        phrase_downloads: Dict[str, List[str]],
        source_filename: str | None = None,
    ) -> str:
        """Organize downloaded files into structured project folders.

        Args:
            job_id: Unique job identifier
            phrase_downloads: Dictionary mapping phrases to lists of downloaded file paths
            source_filename: Name of the original video/audio file that triggered this job

        Returns:
            Path to the organized project folder
        """
        if not phrase_downloads:
            logger.warning(f"No files to organize for job: {job_id}")
            return ""

        project_name = self._generate_project_name(job_id, source_filename)

        project_dir = self.base_output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Organizing files for job {job_id} into: {project_dir}")

        # Create project structure
        organized_files = {}
        total_files_moved = 0

        for phrase, file_paths in phrase_downloads.items():
            if not file_paths:
                continue

            # Create phrase-specific subfolder
            phrase_folder = project_dir / self._sanitize_folder_name(phrase)
            phrase_folder.mkdir(parents=True, exist_ok=True)

            # Move files to phrase folder
            moved_files = []
            for file_path in file_paths:
                try:
                    moved_file = self._move_file_to_folder(file_path, phrase_folder)
                    if moved_file:
                        moved_files.append(moved_file)
                        total_files_moved += 1
                except Exception as e:
                    logger.error(f"Failed to move file {file_path}: {e}")
                    continue

            organized_files[phrase] = moved_files
            logger.info(f"Organized {len(moved_files)} files for phrase: '{phrase}'")

        # Clean up empty phrase directories in the original download location
        self._cleanup_empty_directories()

        logger.info(
            f"File organization completed. Moved {total_files_moved} files to: {project_dir}"
        )
        return str(project_dir)

    def _move_file_to_folder(
        self, source_path: str, destination_folder: Path
    ) -> Optional[str]:
        """Move a file to the destination folder with conflict resolution.

        Args:
            source_path: Path to source file
            destination_folder: Destination folder

        Returns:
            Path to moved file or None if failed
        """
        source = Path(source_path)
        if not source.exists():
            logger.warning(f"Source file does not exist: {source}")
            return None

        # Generate destination path
        destination = destination_folder / source.name

        # Handle filename conflicts
        counter = 1
        original_destination = destination
        while destination.exists():
            stem = original_destination.stem
            suffix = original_destination.suffix
            destination = destination_folder / f"{stem}_{counter}{suffix}"
            counter += 1

        try:
            # Move the file
            shutil.move(str(source), str(destination))
            logger.debug(f"Moved file: {source.name} -> {destination}")
            return str(destination)

        except Exception as e:
            logger.error(f"Failed to move {source} to {destination}: {e}")
            return None

    def _sanitize_folder_name(self, folder_name: str) -> str:
        """Sanitize folder name for filesystem compatibility.

        Args:
            folder_name: Original folder name

        Returns:
            Sanitized folder name
        """
        import re

        sanitized = re.sub(r'[<>:"/\\|?*]', "_", folder_name)
        sanitized = re.sub(r"\s+", "_", sanitized)
        sanitized = sanitized.strip("._ ")

        if not sanitized:
            sanitized = "unnamed_phrase"

        return sanitized[:50]

    def _generate_project_name(
        self, job_id: str, source_filename: str | None = None
    ) -> str:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if source_filename:
            source_base = Path(source_filename).stem
            source_base = self._sanitize_folder_name(source_base)[:30]
            return f"stockpile_{source_base}_{job_id[:8]}_{timestamp}"
        else:
            return f"stockpile_project_{job_id[:8]}_{timestamp}"

    def create_project_structure(
        self, job_id: str, source_filename: str, phrases: List[str]
    ) -> str:
        """Create the complete project folder structure upfront.

        Args:
            job_id: Unique job identifier
            source_filename: Name of the original video/audio file
            phrases: List of search phrases to create folders for

        Returns:
            Path to the created project directory
        """
        project_name = self._generate_project_name(job_id, source_filename)

        project_dir = self.base_output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create phrase subdirectories
        for phrase in phrases:
            phrase_dir = project_dir / self._sanitize_folder_name(phrase)
            phrase_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created project structure: {project_dir} for video {source_filename}")
        return str(project_dir)

    def _cleanup_empty_directories(self) -> None:
        """Clean up empty directories in the base output directory."""
        try:
            # Look for empty phrase directories
            for item in self.base_output_dir.iterdir():
                if item.is_dir() and not any(item.iterdir()):
                    try:
                        item.rmdir()
                        logger.debug(f"Removed empty directory: {item}")
                    except Exception as e:
                        logger.warning(f"Could not remove empty directory {item}: {e}")
        except Exception as e:
            logger.warning(f"Error during directory cleanup: {e}")
