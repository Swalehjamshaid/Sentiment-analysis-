# ==========================================================
# FILE: app/services/memory_service.py
# WORLD-CLASS CONVERSATIONAL MEMORY ENGINE
# ENTERPRISE AI CONTEXT INTELLIGENCE SYSTEM
# ==========================================================

import time
from collections import defaultdict
from typing import Dict, List, Any


# ==========================================================
# MEMORY SERVICE
# ==========================================================

class MemoryService:

    """
    ======================================================
    ENTERPRISE CONVERSATIONAL MEMORY SYSTEM
    ======================================================

    FEATURES:
    - Session memory
    - Context retention
    - Follow-up understanding
    - Conversation continuity
    - Human-like context awareness
    - Smart memory cleanup
    - Intent continuity
    - Executive memory intelligence
    """

    def __init__(self):

        # ==================================================
        # MEMORY STORAGE
        # ==================================================

        self.memory_store = defaultdict(list)

        # ==================================================
        # MEMORY SETTINGS
        # ==================================================

        self.max_memory_per_session = 20

        self.memory_expiry_seconds = 3600

    # ======================================================
    # ADD MEMORY
    # ======================================================

    def add_memory(

        self,
        session_id: str,
        user_message: str,
        ai_response: str,
        metadata: Dict[str, Any] = None

    ):

        try:

            if not session_id:
                return

            if metadata is None:
                metadata = {}

            memory_item = {

                "timestamp":
                    time.time(),

                "user_message":
                    user_message,

                "ai_response":
                    ai_response,

                "metadata":
                    metadata

            }

            self.memory_store[session_id].append(
                memory_item
            )

            # ==============================================
            # LIMIT MEMORY
            # ==============================================

            if len(
                self.memory_store[session_id]
            ) > self.max_memory_per_session:

                self.memory_store[session_id] = (

                    self.memory_store[session_id][
                        -self.max_memory_per_session:
                    ]

                )

            # ==============================================
            # CLEAN EXPIRED MEMORY
            # ==============================================

            self.cleanup_expired_memory()

        except Exception as e:

            print(
                f"❌ Memory Add Error: {e}"
            )

    # ======================================================
    # GET MEMORY
    # ======================================================

    def get_memory(

        self,
        session_id: str,
        limit: int = 10

    ) -> List[Dict]:

        try:

            if session_id not in self.memory_store:
                return []

            memories = self.memory_store[
                session_id
            ]

            return memories[-limit:]

        except Exception as e:

            print(
                f"❌ Memory Get Error: {e}"
            )

            return []

    # ======================================================
    # BUILD CONTEXT
    # ======================================================

    def build_context(

        self,
        session_id: str,
        limit: int = 6

    ) -> str:

        try:

            memories = self.get_memory(
                session_id,
                limit
            )

            if not memories:
                return ""

            context_parts = []

            for memory in memories:

                user_message = memory.get(
                    "user_message",
                    ""
                )

                ai_response = memory.get(
                    "ai_response",
                    ""
                )

                # ==========================================
                # LIMIT RESPONSE SIZE
                # ==========================================

                ai_response = ai_response[:300]

                context_parts.append(

                    f"""
User:
{user_message}

AI:
{ai_response}
"""

                )

            return "\n".join(
                context_parts
            )

        except Exception as e:

            print(
                f"❌ Context Build Error: {e}"
            )

            return ""

    # ======================================================
    # LAST USER MESSAGE
    # ======================================================

    def get_last_user_message(

        self,
        session_id: str

    ):

        try:

            memories = self.get_memory(
                session_id,
                limit=1
            )

            if not memories:
                return None

            return memories[-1].get(
                "user_message"
            )

        except Exception as e:

            print(
                f"❌ Last Message Error: {e}"
            )

            return None

    # ======================================================
    # LAST AI RESPONSE
    # ======================================================

    def get_last_ai_response(

        self,
        session_id: str

    ):

        try:

            memories = self.get_memory(
                session_id,
                limit=1
            )

            if not memories:
                return None

            return memories[-1].get(
                "ai_response"
            )

        except Exception as e:

            print(
                f"❌ Last AI Error: {e}"
            )

            return None

    # ======================================================
    # FOLLOW-UP DETECTION
    # ======================================================

    def is_followup_question(

        self,
        session_id: str,
        current_query: str

    ) -> bool:

        try:

            followup_patterns = [

                "tell me more",
                "more",
                "why",
                "how",
                "explain",
                "what about",
                "give short answer",
                "give detailed answer",
                "summarize",
                "one sentence",
                "bullet points",
                "what else",
                "and",
                "continue"

            ]

            current_query = current_query.lower()

            if any(

                pattern in current_query

                for pattern in followup_patterns

            ):

                previous_memory = self.get_memory(
                    session_id,
                    limit=1
                )

                return len(
                    previous_memory
                ) > 0

            return False

        except Exception as e:

            print(
                f"❌ Followup Detection Error: {e}"
            )

            return False

    # ======================================================
    # CONTEXTUAL QUERY
    # ======================================================

    def build_contextual_query(

        self,
        session_id: str,
        current_query: str

    ):

        try:

            if not self.is_followup_question(

                session_id,
                current_query

            ):

                return current_query

            last_message = self.get_last_user_message(
                session_id
            )

            if not last_message:
                return current_query

            contextual_query = f"""

PREVIOUS USER QUESTION:
{last_message}

FOLLOW-UP QUESTION:
{current_query}

"""

            return contextual_query.strip()

        except Exception as e:

            print(
                f"❌ Contextual Query Error: {e}"
            )

            return current_query

    # ======================================================
    # MEMORY SUMMARY
    # ======================================================

    def summarize_memory(

        self,
        session_id: str

    ):

        try:

            memories = self.get_memory(
                session_id,
                limit=10
            )

            if not memories:
                return ""

            user_topics = []

            for memory in memories:

                user_message = memory.get(
                    "user_message",
                    ""
                )

                user_topics.append(
                    user_message
                )

            summary = " | ".join(
                user_topics[-5:]
            )

            return summary

        except Exception as e:

            print(
                f"❌ Memory Summary Error: {e}"
            )

            return ""

    # ======================================================
    # CLEAN EXPIRED MEMORY
    # ======================================================

    def cleanup_expired_memory(self):

        try:

            current_time = time.time()

            expired_sessions = []

            for session_id, memories in self.memory_store.items():

                valid_memories = []

                for memory in memories:

                    timestamp = memory.get(
                        "timestamp",
                        0
                    )

                    age = current_time - timestamp

                    if age < self.memory_expiry_seconds:

                        valid_memories.append(
                            memory
                        )

                self.memory_store[
                    session_id
                ] = valid_memories

                if not valid_memories:

                    expired_sessions.append(
                        session_id
                    )

            # ==============================================
            # REMOVE EMPTY SESSIONS
            # ==============================================

            for session_id in expired_sessions:

                del self.memory_store[
                    session_id
                ]

        except Exception as e:

            print(
                f"❌ Memory Cleanup Error: {e}"
            )

    # ======================================================
    # CLEAR SESSION MEMORY
    # ======================================================

    def clear_session_memory(

        self,
        session_id: str

    ):

        try:

            if session_id in self.memory_store:

                del self.memory_store[
                    session_id
                ]

        except Exception as e:

            print(
                f"❌ Clear Memory Error: {e}"
            )

    # ======================================================
    # MEMORY STATS
    # ======================================================

    def get_memory_stats(self):

        try:

            total_sessions = len(
                self.memory_store
            )

            total_messages = sum(

                len(memories)

                for memories in self.memory_store.values()

            )

            return {

                "total_sessions":
                    total_sessions,

                "total_messages":
                    total_messages,

                "memory_limit":
                    self.max_memory_per_session,

                "expiry_seconds":
                    self.memory_expiry_seconds

            }

        except Exception as e:

            print(
                f"❌ Memory Stats Error: {e}"
            )

            return {}


# ==========================================================
# GLOBAL INSTANCE
# ==========================================================

memory_service = MemoryService()
