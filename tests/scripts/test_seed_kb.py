"""Tests for the KB seed script."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.seed_kb import chunk_file, get_priority_files, should_skip


class TestShouldSkip:
    def test_skips_node_modules(self):
        assert should_skip(Path("project/node_modules/foo.js")) is True

    def test_skips_git_dir(self):
        assert should_skip(Path("project/.git/config")) is True

    def test_skips_pycache(self):
        assert should_skip(Path("project/__pycache__/foo.pyc")) is True

    def test_skips_lock_files(self):
        assert should_skip(Path("project/package-lock.json")) is True

    def test_skips_dist(self):
        assert should_skip(Path("project/dist/bundle.js")) is True

    def test_allows_readme(self):
        assert should_skip(Path("project/README.md")) is False

    def test_allows_python_source(self):
        assert should_skip(Path("project/main.py")) is False


class TestChunkFile:
    def test_small_file_is_single_chunk(self):
        content = "line1\nline2\nline3"
        chunks = chunk_file(content, max_tokens=500)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_large_file_is_split(self):
        # 1000 words → should split at ~500 tokens (≈375 words)
        content = "\n\n".join(["word " * 50] * 20)
        chunks = chunk_file(content, max_tokens=500)
        assert len(chunks) > 1


class TestGetPriorityFiles:
    def test_finds_readme(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "README.md").write_text("# Test")
            Path(tmpdir, "main.py").write_text("print('hi')")
            Path(tmpdir, "node_modules").mkdir()
            Path(tmpdir, "node_modules", "foo.js").write_text("x")
            files = get_priority_files(Path(tmpdir))
            names = [f.name for f in files]
            assert "README.md" in names
            assert "main.py" in names
            assert "foo.js" not in names
