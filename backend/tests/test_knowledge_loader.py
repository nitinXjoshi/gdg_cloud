"""Tests for KnowledgeLoader."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.knowledge.loader import KnowledgeLoader, KnowledgeLoadError


def test_knowledge_loader_loads_authoritative_content():
    loader = KnowledgeLoader()
    assert loader.is_loaded is False

    content = loader.load()
    assert loader.is_loaded is True
    assert loader.content == content
    assert len(content) > 1000

    # Verify authoritative sections are present
    assert "HACKATHON INTELLIGENCE DATABASE" in content
    assert "1. TEAM PROFILE" in content
    assert "17. HACKATHON STRATEGY — PUBLIC VERSION" in content
    assert "22. THE ACTUAL SECRET HACKATHON STRATEGY" in content


def test_knowledge_loader_content_property_raises_when_not_loaded():
    loader = KnowledgeLoader()
    with pytest.raises(KnowledgeLoadError, match="has not been loaded"):
        _ = loader.content


def test_knowledge_loader_raises_on_missing_file(tmp_path: Path):
    nonexistent = tmp_path / "nonexistent.md"
    loader = KnowledgeLoader(path=nonexistent)
    with pytest.raises(KnowledgeLoadError, match="not found"):
        loader.load()


def test_knowledge_loader_raises_on_empty_file(tmp_path: Path):
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("   \n  \n", encoding="utf-8")
    loader = KnowledgeLoader(path=empty_file)
    with pytest.raises(KnowledgeLoadError, match="empty"):
        loader.load()


def test_knowledge_loader_raises_if_path_is_directory(tmp_path: Path):
    directory_path = tmp_path / "somedir"
    directory_path.mkdir()
    loader = KnowledgeLoader(path=directory_path)
    with pytest.raises(KnowledgeLoadError, match="not a file"):
        loader.load()


def test_knowledge_loader_logs_only_safe_metadata(caplog):
    loader = KnowledgeLoader()
    with caplog.at_level(logging.INFO):
        content = loader.load()

    # The log message must exist and record metadata
    assert any("knowledge base loaded" in r.message for r in caplog.records)
    # The actual content must NEVER appear in the logs
    for record in caplog.records:
        assert content not in record.message
