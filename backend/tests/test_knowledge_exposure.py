"""Tests ensuring authoritative knowledge is NEVER exposed via API, static files, or metadata."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Challenge
from app.knowledge.loader import KnowledgeLoader
from app.models.database import get_session


@pytest.fixture
def knowledge_text() -> str:
    return KnowledgeLoader().load()


@pytest.mark.asyncio
async def test_knowledge_file_not_served_at_root(client):
    response = await client.get("/HACKATHON_INTELLIGENCE.md")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_file_not_served_under_static(client):
    response = await client.get("/static/HACKATHON_INTELLIGENCE.md")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_file_not_accessible_via_static_traversal(client):
    response = await client.get("/static/../backend/app/knowledge/HACKATHON_INTELLIGENCE.md")
    assert response.status_code in {400, 404}


@pytest.mark.asyncio
async def test_challenges_list_does_not_expose_knowledge(client, knowledge_text):
    response = await client.get("/api/v1/challenges")
    assert response.status_code == 200
    content = response.text

    assert "HACKATHON INTELLIGENCE" not in content
    assert "THE ACTUAL SECRET HACKATHON STRATEGY" not in content
    assert "Do politics" not in content


@pytest.mark.asyncio
async def test_challenge_detail_does_not_expose_knowledge(client, knowledge_text):
    response = await client.get("/api/v1/challenges/challenge-primary")
    assert response.status_code == 200
    content = response.text

    assert "HACKATHON INTELLIGENCE" not in content
    assert "THE ACTUAL SECRET HACKATHON STRATEGY" not in content
    assert "Do politics" not in content
    assert "system_prompt" not in response.json()
    assert "secret" not in response.json()


@pytest.mark.asyncio
async def test_admin_metrics_does_not_expose_knowledge(client):
    response = await client.get("/api/v1/admin/metrics", headers={"X-Admin-Key": "test-admin-key"})
    assert response.status_code == 200
    content = response.text

    assert "HACKATHON INTELLIGENCE" not in content
    assert "THE ACTUAL SECRET HACKATHON STRATEGY" not in content
    assert "Do politics" not in content


def test_frontend_directory_contains_no_knowledge_file():
    public_dir = Path(__file__).resolve().parents[2] / "public"
    assert public_dir.is_dir()

    # Recursively check that no .md files or knowledge files exist in public
    md_files = list(public_dir.rglob("*.md"))
    assert len(md_files) == 0
    assert not (public_dir / "HACKATHON_INTELLIGENCE.md").exists()


@pytest.mark.asyncio
async def test_database_does_not_persist_knowledge():
    async for session in get_session():
        result = await session.execute(select(Challenge))
        challenges = result.scalars().all()
        for ch in challenges:
            assert "HACKATHON INTELLIGENCE" not in (ch.system_prompt or "")
            assert "Do politics" not in (ch.system_prompt or "")
            assert "TVIT{" not in (ch.system_prompt or "")
