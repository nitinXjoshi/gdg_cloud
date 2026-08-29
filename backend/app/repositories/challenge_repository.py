"""Repository for challenge and participant/session persistence.

Challenges are bootstrapped from the in-memory ``ChallengeDefinition`` objects
so the runtime flag stays out of the database, but their public metadata is
stored so relational queries (joins, counts) work cleanly.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_token
from app.db.models import Challenge, Participant, Session


class ChallengeRepository:
    async def upsert(self, session: AsyncSession, definition) -> Challenge:
        result = await session.execute(
            select(Challenge).where(Challenge.id == definition.challenge_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.name = definition.name
            existing.description = definition.description
            existing.difficulty = definition.difficulty
            existing.model = definition.model
            existing.max_output_tokens = definition.max_output_tokens
            existing.enabled = definition.enabled
            await session.flush()
            return existing

        challenge = Challenge(
            id=definition.challenge_id,
            name=definition.name,
            description=definition.description,
            # Never persist the flag; store an empty placeholder for the column.
            system_prompt="",
            difficulty=definition.difficulty,
            model=definition.model,
            max_output_tokens=definition.max_output_tokens,
            enabled=definition.enabled,
        )
        session.add(challenge)
        await session.flush()
        return challenge

    async def get(self, session: AsyncSession, challenge_id: str) -> Challenge | None:
        result = await session.execute(select(Challenge).where(Challenge.id == challenge_id))
        return result.scalar_one_or_none()

    async def list(self, session: AsyncSession) -> list[Challenge]:
        result = await session.execute(select(Challenge).order_by(Challenge.created_at))
        return list(result.scalars())


class ParticipantRepository:
    async def create_participant(self, session: AsyncSession) -> Participant:
        participant = Participant()
        session.add(participant)
        await session.flush()
        return participant

    async def create_session(
        self,
        session: AsyncSession,
        participant: Participant,
        *,
        expires_at,
    ) -> tuple[Session, str]:
        raw_token = generate_token()
        db_session = Session(
            participant_id=participant.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        session.add(db_session)
        await session.flush()
        return db_session, raw_token

    async def get_session_by_token_hash(
        self, session: AsyncSession, token_hash: str
    ) -> Session | None:
        result = await session.execute(select(Session).where(Session.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def count(self, session: AsyncSession) -> int:
        result = await session.execute(select(Participant.id))
        return len(result.scalars().all())
