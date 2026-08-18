"""Conversation-thread persistence: create/list/read/delete threads, and
read/write the messages inside them. Single-user for tonight's demo — no
`user_id` column yet, but adding one later just adds a WHERE clause, it
doesn't restructure these tables (see setup_conversations.sql).
"""

from datetime import datetime, timezone

from document_id import answer_within_document
from retrieval import supabase

TITLE_MAX_LEN = 60


def make_title(question):
    question = question.strip().replace("\n", " ")
    return question[:TITLE_MAX_LEN]


def create_thread(question, source_document):
    result = (
        supabase.table("conversation_threads")
        .insert({"title": make_title(question), "source_document": source_document})
        .execute()
    )
    return result.data[0]["session_id"]


def touch_thread(session_id):
    supabase.table("conversation_threads").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("session_id", session_id).execute()


def list_threads():
    result = (
        supabase.table("conversation_threads")
        .select("session_id, title, source_document, updated_at")
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


def get_thread(session_id):
    result = (
        supabase.table("conversation_threads")
        .select("session_id, title, source_document")
        .eq("session_id", session_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_messages(session_id):
    result = (
        supabase.table("conversation_messages")
        .select("role, content")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return result.data


def add_message(session_id, role, content):
    supabase.table("conversation_messages").insert(
        {"session_id": session_id, "role": role, "content": content}
    ).execute()


def delete_thread(session_id):
    supabase.table("conversation_threads").delete().eq("session_id", session_id).execute()


def ask_and_persist(question, source_document, session_id=None):
    """Answer a question about a document, persisting both turns and the
    thread itself. Shared by the FastAPI backend (api.py) and the MCP server
    (mcp_server.py) so a conversation started from one interface behaves
    identically to one started from the other — same thread, same memory."""
    if session_id is None:
        session_id = create_thread(question, source_document)
        history = []
    else:
        history = get_messages(session_id)

    result = answer_within_document(question, source_document, history)

    add_message(session_id, "user", question)
    add_message(session_id, "assistant", result["answer"])
    touch_thread(session_id)

    result["session_id"] = session_id
    return result
