"""File organization service for structuring B-roll downloads."""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

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
    
    def organize_files(self, job_id: str, phrase_downloads: Dict[str, List[str]]) -> str:
        """Organize downloaded files into structured project folders.
        
        Args:
            job_id: Unique job identifier
            phrase_downloads: Dictionary mapping phrases to lists of downloaded file paths
            
        Returns:
            Path to the organized project folder
        """
        if not phrase_downloads:
            logger.warning(f"No files to organize for job: {job_id}")
            return ""
        
        # Create project folder with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"broll_project_{job_id[:8]}_{timestamp}"
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
        
        # Create project summary file
        self._create_project_summary(project_dir, job_id, organized_files)
        
        # Clean up empty phrase directories in the original download location
        self._cleanup_empty_directories()
        
        logger.info(f"File organization completed. Moved {total_files_moved} files to: {project_dir}")
        return str(project_dir)
    
    def _move_file_to_folder(self, source_path: str, destination_folder: Path) -> Optional[str]:
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
        
        # Replace invalid characters with underscores
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', folder_name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        
        # Ensure it's not empty and not too long
        if not sanitized:
            sanitized = 'unnamed_phrase'
        
        return sanitized[:50]  # Limit length
    
    def _create_project_summary(self, project_dir: Path, job_id: str, organized_files: Dict[str, List[str]]) -> None:
        """Create a summary file for the project.
        
        Args:
            project_dir: Project directory
            job_id: Job identifier
            organized_files: Dictionary of organized files by phrase
        """
        summary_file = project_dir / "PROJECT_SUMMARY.txt"
        
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write("B-ROLL PROJECT SUMMARY\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Job ID: {job_id}\n")
                f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Project Directory: {project_dir.name}\n\n")
                
                f.write("ORGANIZED FILES BY SEARCH PHRASE:\n")
                f.write("-" * 40 + "\n\n")
                
                total_files = 0
                for phrase, files in organized_files.items():
                    f.write(f"Search Phrase: '{phrase}'\n")
                    f.write(f"Files ({len(files)}):\n")
                    
                    for file_path in files:
                        file_name = Path(file_path).name
                        file_size = self._get_file_size_mb(file_path)
                        f.write(f"  - {file_name} ({file_size} MB)\n")
                    
                    f.write("\n")
                    total_files += len(files)
                
                f.write(f"TOTAL FILES: {total_files}\n")
                f.write(f"TOTAL PROJECT SIZE: {self._get_directory_size_mb(project_dir)} MB\n")
            
            logger.info(f"Created project summary: {summary_file}")
            
        except Exception as e:
            logger.error(f"Failed to create project summary: {e}")
    
    def _get_file_size_mb(self, file_path: str) -> str:
        """Get file size in MB as formatted string.
        
        Args:
            file_path: Path to file
            
        Returns:
            File size as formatted string
        """
        try:
            size_bytes = Path(file_path).stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            return f"{size_mb:.1f}"
        except Exception:
            return "Unknown"
    
    def _get_directory_size_mb(self, directory: Path) -> str:
        """Get total directory size in MB as formatted string.
        
        Args:
            directory: Directory path
            
        Returns:
            Directory size as formatted string
        """
        try:
            total_size = sum(
                f.stat().st_size for f in directory.rglob('*') if f.is_file()
            )
            size_mb = total_size / (1024 * 1024)
            return f"{size_mb:.1f}"
        except Exception:
            return "Unknown"
    
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
    
    def get_project_info(self, project_path: str) -> Dict:
        """Get information about an organized project.
        
        Args:
            project_path: Path to project directory
            
        Returns:
            Dictionary with project information
        """
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": "Project directory not found"}
        
        try:
            # Count files and folders
            phrase_folders = [d for d in project_dir.iterdir() if d.is_dir()]
            total_files = sum(
                len([f for f in folder.iterdir() if f.is_file()]) 
                for folder in phrase_folders
            )
            
            return {
                "project_name": project_dir.name,
                "phrase_count": len(phrase_folders),
                "total_files": total_files,
                "total_size_mb": self._get_directory_size_mb(project_dir),
                "phrases": [folder.name for folder in phrase_folders]
            }
            
        except Exception as e:
            logger.error(f"Error getting project info for {project_path}: {e}")
            return {"error": str(e)}