"""FileCheckpoint - Version control system for BigBrain projects."""

import json
import shutil
import tarfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class FileCheckpoint:
    """
    File checkpointing system for project state management.
    
    Provides snapshot/restore functionality for project directories,
    allowing recovery from errors and comparison of changes.
    
    Storage format:
    - Each checkpoint is stored as a compressed tar.gz file
    - Metadata stored in .checkpoints/metadata.json
    - Auto-cleanup of old checkpoints (keeps last 10)
    """
    
    def __init__(self, max_checkpoints: int = 10):
        """
        Initialize checkpoint manager.
        
        Args:
            max_checkpoints: Maximum number of checkpoints to keep per project
        """
        self.max_checkpoints = max_checkpoints
    
    def snapshot(self, project_dir: Path) -> str:
        """
        Create a snapshot of all files in the project directory.
        
        Args:
            project_dir: Path to the project directory to snapshot
            
        Returns:
            Checkpoint ID (UUID string) for the created snapshot
            
        Raises:
            ValueError: If project directory doesn't exist
            RuntimeError: If snapshot creation fails
        """
        if not project_dir.exists() or not project_dir.is_dir():
            raise ValueError(f"Project directory not found: {project_dir}")
        
        # Create .checkpoints directory
        checkpoints_dir = project_dir / ".checkpoints"
        checkpoints_dir.mkdir(exist_ok=True)
        
        # Generate unique checkpoint ID
        checkpoint_id = str(uuid.uuid4())
        timestamp = time.time()
        
        # Create tar.gz archive of all project files (excluding .checkpoints)
        archive_path = checkpoints_dir / f"{checkpoint_id}.tar.gz"
        
        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for item in project_dir.iterdir():
                    if item.name != ".checkpoints":
                        # Use relative path in archive
                        tar.add(item, arcname=item.name, recursive=True)
            
            # Update metadata
            self._update_metadata(checkpoints_dir, checkpoint_id, timestamp, project_dir)
            
            # Cleanup old checkpoints
            self._cleanup_old_checkpoints(checkpoints_dir)
            
            logger.info("Created checkpoint %s for %s", checkpoint_id[:8], project_dir.name)
            return checkpoint_id
            
        except Exception as e:
            # Cleanup partial archive on failure
            if archive_path.exists():
                archive_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to create checkpoint: {str(e)}") from e
    
    def restore(self, checkpoint_id: str, project_dir: Path) -> None:
        """
        Restore project directory from a checkpoint.
        
        Args:
            checkpoint_id: Checkpoint ID to restore from
            project_dir: Path to restore the checkpoint to
            
        Raises:
            ValueError: If checkpoint doesn't exist
            RuntimeError: If restore fails
        """
        checkpoints_dir = project_dir / ".checkpoints"
        archive_path = checkpoints_dir / f"{checkpoint_id}.tar.gz"
        
        if not archive_path.exists():
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        
        # Create project directory if it doesn't exist
        project_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Clear existing files (except .checkpoints)
            for item in project_dir.iterdir():
                if item.name != ".checkpoints":
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
            
            # Extract archive
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=project_dir)
            
            logger.info("Restored checkpoint %s to %s", checkpoint_id[:8], project_dir.name)
            
        except Exception as e:
            raise RuntimeError(f"Failed to restore checkpoint {checkpoint_id}: {str(e)}") from e
    
    def list_checkpoints(self, project_dir: Path) -> List[Dict[str, Any]]:
        """
        List all available checkpoints for a project.
        
        Args:
            project_dir: Path to the project directory
            
        Returns:
            List of checkpoint info dictionaries with keys:
            - id: checkpoint ID
            - timestamp: creation timestamp
            - created_at: human-readable creation time
            - size_bytes: archive size in bytes
            - files_count: number of files in the checkpoint
        """
        checkpoints_dir = project_dir / ".checkpoints"
        if not checkpoints_dir.exists():
            return []
        
        metadata_file = checkpoints_dir / "metadata.json"
        if not metadata_file.exists():
            return []
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            checkpoints = []
            for checkpoint_id, info in metadata.get("checkpoints", {}).items():
                archive_path = checkpoints_dir / f"{checkpoint_id}.tar.gz"
                if archive_path.exists():
                    size_bytes = archive_path.stat().st_size
                    checkpoints.append({
                        "id": checkpoint_id,
                        "timestamp": info.get("timestamp", 0),
                        "created_at": info.get("created_at", "Unknown"),
                        "size_bytes": size_bytes,
                        "files_count": info.get("files_count", 0)
                    })
            
            # Sort by timestamp (newest first)
            return sorted(checkpoints, key=lambda x: x["timestamp"], reverse=True)
            
        except Exception as e:
            logger.warning("Failed to load checkpoint metadata: %s", e)
            return []
    
    def diff(self, checkpoint_id: str, project_dir: Path) -> Dict[str, Any]:
        """
        Show what has changed since a specific checkpoint.
        
        Args:
            checkpoint_id: Checkpoint ID to compare against
            project_dir: Current project directory
            
        Returns:
            Dictionary with change summary:
            - added: list of newly added files
            - modified: list of files that changed
            - deleted: list of files that were removed
            - unchanged: count of files that haven't changed
        """
        checkpoints_dir = project_dir / ".checkpoints"
        archive_path = checkpoints_dir / f"{checkpoint_id}.tar.gz"
        
        if not archive_path.exists():
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        
        try:
            # Extract checkpoint to a temporary location for comparison
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / "checkpoint"
                temp_path.mkdir()
                
                # Extract checkpoint
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(path=temp_path)
                
                # Compare current state with checkpoint
                changes = self._compare_directories(temp_path, project_dir)
                return changes
                
        except Exception as e:
            raise RuntimeError(f"Failed to compute diff for checkpoint {checkpoint_id}: {str(e)}") from e
    
    def _update_metadata(self, checkpoints_dir: Path, checkpoint_id: str,
                        timestamp: float, project_dir: Path) -> None:
        """Update checkpoint metadata file."""
        metadata_file = checkpoints_dir / "metadata.json"
        
        # Load existing metadata
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, IOError):
                metadata = {"checkpoints": {}}
        else:
            metadata = {"checkpoints": {}}
        
        # Count files in project (excluding .checkpoints)
        files_count = sum(1 for item in project_dir.rglob("*") 
                         if item.is_file() and ".checkpoints" not in item.parts)
        
        # Add new checkpoint entry
        metadata["checkpoints"][checkpoint_id] = {
            "timestamp": timestamp,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "files_count": files_count
        }
        
        # Save metadata
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    
    def _cleanup_old_checkpoints(self, checkpoints_dir: Path) -> None:
        """Remove old checkpoints to stay within max_checkpoints limit."""
        metadata_file = checkpoints_dir / "metadata.json"
        
        if not metadata_file.exists():
            return
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            checkpoints = metadata.get("checkpoints", {})
            if len(checkpoints) <= self.max_checkpoints:
                return
            
            # Sort by timestamp and keep only the most recent ones
            sorted_checkpoints = sorted(
                checkpoints.items(),
                key=lambda x: x[1].get("timestamp", 0),
                reverse=True
            )
            
            to_keep = sorted_checkpoints[:self.max_checkpoints]
            to_remove = sorted_checkpoints[self.max_checkpoints:]
            
            # Remove old checkpoint files and metadata entries
            for checkpoint_id, _ in to_remove:
                archive_path = checkpoints_dir / f"{checkpoint_id}.tar.gz"
                archive_path.unlink(missing_ok=True)
                checkpoints.pop(checkpoint_id, None)
            
            # Update metadata
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            if to_remove:
                logger.info("Cleaned up %d old checkpoints", len(to_remove))
            
        except Exception as e:
            logger.warning("Failed to cleanup old checkpoints: %s", e)
    
    def _compare_directories(self, checkpoint_dir: Path, current_dir: Path) -> Dict[str, Any]:
        """Compare two directories and return change summary."""
        def get_file_info(directory: Path) -> Dict[str, Dict[str, Any]]:
            """Get file info (path, size, mtime) for all files in directory."""
            files = {}
            for item in directory.rglob("*"):
                if item.is_file() and ".checkpoints" not in item.parts:
                    rel_path = item.relative_to(directory)
                    files[str(rel_path)] = {
                        "size": item.stat().st_size,
                        "mtime": item.stat().st_mtime
                    }
            return files
        
        checkpoint_files = get_file_info(checkpoint_dir)
        current_files = get_file_info(current_dir)
        
        added = []
        modified = []
        deleted = []
        unchanged = 0
        
        # Find added and modified files
        for file_path, current_info in current_files.items():
            if file_path not in checkpoint_files:
                added.append(file_path)
            else:
                checkpoint_info = checkpoint_files[file_path]
                if (current_info["size"] != checkpoint_info["size"] or
                    abs(current_info["mtime"] - checkpoint_info["mtime"]) > 1):
                    modified.append(file_path)
                else:
                    unchanged += 1
        
        # Find deleted files
        for file_path in checkpoint_files:
            if file_path not in current_files:
                deleted.append(file_path)
        
        return {
            "added": sorted(added),
            "modified": sorted(modified), 
            "deleted": sorted(deleted),
            "unchanged": unchanged,
            "total_changes": len(added) + len(modified) + len(deleted)
        }