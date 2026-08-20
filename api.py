"""FastAPI layer: paste a snippet, get the source document, then chat about
it with server-side memory (conversation_threads/conversation_messages).

No auth yet (PRD_v1.1.md Goal P1 #9 — deferred; single-user for now).
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import conversations
from document_id import identify_source

app = FastAPI(title="Sinolume Internal Analyst Companion API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class IdentifyRequest(BaseModel):
    snippet: str


class AskRequest(BaseModel):
    question: str
    source_document: str
    session_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/identify")
def identify(req: IdentifyRequest):
    return identify_source(req.snippet)


@app.post("/ask")
def ask(req: AskRequest):
    return conversations.ask_and_persist(req.question, req.source_document, req.session_id)


@app.get("/conversations")
def conversations_list():
    return conversations.list_threads()


@app.get("/conversations/{session_id}")
def conversation_detail(session_id: str):
    thread = conversations.get_thread(session_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    thread["messages"] = conversations.get_messages(session_id)
    return thread


@app.delete("/conversations/{session_id}")
def conversation_delete(session_id: str):
    conversations.delete_thread(session_id)
    return {"deleted": True}
