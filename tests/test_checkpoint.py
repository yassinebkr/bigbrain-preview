"""Tests for FileCheckpoint system."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from bigbrain.orchestrator.checkpoint import FileCheckpoint


class TestFileCheckpoint:
    """Test FileCheckpoint functionality."""

    def test_create_checkpoint_manager(self):
        manager = FileCheckpoint(max_checkpoints=5)
        assert manager.max_checkpoints == 5
        default_manager = FileCheckpoint()
        assert default_manager.max_checkpoints == 10

    def test_snapshot_nonexistent_directory(self):
        manager = FileCheckpoint()
        with pytest.raises(ValueError, match="Project directory not found"):
            manager.snapshot(Path("/nonexistent/directory"))

    def test_snapshot_creates_archive(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "a.py").write_text("print('a')")
            cid = manager.snapshot(proj)
            assert isinstance(cid, str)
            assert (proj / ".checkpoints" / f"{cid}.tar.gz").exists()

    def test_snapshot_and_restore_full_cycle(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "f1.txt").write_text("original1")
            (proj / "f2.txt").write_text("original2")
            sub = proj / "sub"
            sub.mkdir()
            (sub / "f3.txt").write_text("original3")

            cid = manager.snapshot(proj)

            # Modify state
            (proj / "f1.txt").write_text("MODIFIED")
            (proj / "f2.txt").unlink()
            (proj / "new.txt").write_text("new file")

            manager.restore(cid, proj)

            assert (proj / "f1.txt").read_text() == "original1"
            assert (proj / "f2.txt").read_text() == "original2"
            assert (sub / "f3.txt").read_text() == "original3"
            assert not (proj / "new.txt").exists()

    def test_restore_nonexistent_checkpoint(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            with pytest.raises(ValueError, match="Checkpoint not found"):
                manager.restore("bad-id", proj)

    def test_list_checkpoints_empty(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            assert manager.list_checkpoints(proj) == []

    def test_list_checkpoints_order(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "x.txt").write_text("x")

            c1 = manager.snapshot(proj)
            time.sleep(0.05)
            c2 = manager.snapshot(proj)

            cps = manager.list_checkpoints(proj)
            assert len(cps) == 2
            # Newest first
            assert cps[0]["id"] == c2
            assert cps[1]["id"] == c1

    def test_list_checkpoints_structure(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "a.txt").write_text("a")
            manager.snapshot(proj)
            cps = manager.list_checkpoints(proj)
            cp = cps[0]
            assert "id" in cp
            assert "timestamp" in cp
            assert "created_at" in cp
            assert "size_bytes" in cp
            assert cp["size_bytes"] > 0
            assert "files_count" in cp
            assert cp["files_count"] == 1

    def test_diff_added_modified_deleted(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "keep.txt").write_text("keep")
            (proj / "modify.txt").write_text("old")
            (proj / "delete.txt").write_text("bye")

            cid = manager.snapshot(proj)

            (proj / "modify.txt").write_text("NEW CONTENT")
            (proj / "delete.txt").unlink()
            (proj / "added.txt").write_text("hello")

            diff = manager.diff(cid, proj)
            assert "added.txt" in diff["added"]
            assert "modify.txt" in diff["modified"]
            assert "delete.txt" in diff["deleted"]
            assert diff["total_changes"] == 3

    def test_diff_nonexistent_checkpoint(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            with pytest.raises(ValueError, match="Checkpoint not found"):
                manager.diff("nope", proj)

    def test_cleanup_old_checkpoints(self):
        manager = FileCheckpoint(max_checkpoints=3)
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "x.txt").write_text("x")

            ids = []
            for _ in range(5):
                ids.append(manager.snapshot(proj))
                time.sleep(0.05)

            cps = manager.list_checkpoints(proj)
            assert len(cps) == 3
            remaining = {cp["id"] for cp in cps}
            # Should keep the 3 newest
            assert remaining == set(ids[-3:])

    def test_checkpoints_dir_excluded_from_snapshot(self):
        """Ensure .checkpoints directory is not included in the archive."""
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "real.txt").write_text("real")

            c1 = manager.snapshot(proj)
            c2 = manager.snapshot(proj)

            # Restore first checkpoint — .checkpoints should still exist
            manager.restore(c1, proj)
            assert (proj / ".checkpoints").exists()
            assert (proj / "real.txt").read_text() == "real"

    def test_metadata_persistence(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "a.txt").write_text("a")
            (proj / "b.txt").write_text("b")
            cid = manager.snapshot(proj)

            meta_path = proj / ".checkpoints" / "metadata.json"
            assert meta_path.exists()
            meta = json.loads(meta_path.read_text())
            assert cid in meta["checkpoints"]
            assert meta["checkpoints"][cid]["files_count"] == 2

    def test_corrupted_metadata_returns_empty(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            cpdir = proj / ".checkpoints"
            cpdir.mkdir()
            (cpdir / "metadata.json").write_text("{{{BROKEN")
            assert manager.list_checkpoints(proj) == []

    def test_compare_identical_directories(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            d1 = Path(td) / "a"
            d2 = Path(td) / "b"
            d1.mkdir()
            d2.mkdir()
            changes = manager._compare_directories(d1, d2)
            assert changes["total_changes"] == 0

    def test_compare_with_new_file(self):
        manager = FileCheckpoint()
        with tempfile.TemporaryDirectory() as td:
            d1 = Path(td) / "old"
            d2 = Path(td) / "new"
            d1.mkdir()
            d2.mkdir()
            (d2 / "added.py").write_text("new")
            changes = manager._compare_directories(d1, d2)
            assert "added.py" in changes["added"]
