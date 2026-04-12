"""
ConversationService — PostgreSQL-backed conversation history.

Wraps the conversations + messages tables and provides:
  - load_history(conversation_id)  → list of {role, content} dicts for Claude
  - save_exchange(conversation_id, user_task, assistant_result) → persists turn
  - get_or_create_conversation(conversation_id) → ensure row exists, return id
"""

from __future__ import annotations

from typing import Any, Dict, List


class ConversationService:
    """Manages conversation persistence for CRUZ agents."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def load_history(self, conversation_id: str) -> List[Dict[str, str]]:
        """
        Load the last 50 messages for a conversation in chronological order.

        Returns a list of {role, content} dicts ready to prepend to Claude's
        messages array. Extra DB fields (id, created_at, etc.) are stripped.
        """
        rows = await self._db.fetch(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            LIMIT 50
            """,
            conversation_id,
        )
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def save_exchange(
        self,
        conversation_id: str,
        user_task: str,
        assistant_result: str,
    ) -> None:
        """
        Persist a user/assistant turn to the messages table.

        Inserts two rows — one for the user message, one for the assistant
        response — using PostgreSQL's DEFAULT for the UUID primary key and
        created_at timestamp.
        """
        await self._db.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES ($1, 'user', $2)
            """,
            conversation_id,
            user_task,
        )
        await self._db.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES ($1, 'assistant', $2)
            """,
            conversation_id,
            assistant_result,
        )

    async def get_or_create_conversation(self, conversation_id: str) -> str:
        """
        Ensure the conversation row exists, creating it if needed.

        Returns the conversation_id unchanged (callers always have the id —
        this just guarantees the FK constraint is satisfied before saving
        messages).
        """
        existing = await self._db.fetchrow(
            "SELECT id FROM conversations WHERE id = $1",
            conversation_id,
        )
        if existing is not None:
            return conversation_id

        await self._db.execute(
            "INSERT INTO conversations (id) VALUES ($1)",
            conversation_id,
        )
        return conversation_id
