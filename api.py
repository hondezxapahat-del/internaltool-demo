"""FastAPI layer: paste a snippet, get the source document, then chat about
it with server-side memory (conversation_threads/conversation_messages).

Every endpoint except /health and /auth/login requires a login token
(PRD_v1.2.md Requirements 19-21) — there is no self-service signup, an
account must already exist (see create_user.py).

Also mounts the MCP server (mcp_server.py) at /mcp over streamable-http, so
the exact same deployment serves both the web frontend and a remote MCP
client — one Render service, not two.
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

import auth
import conversations
from document_id import identify_source
from mcp_server import mcp

# streamable_http_path="/" so mounting this at "/mcp" below gives a clean
# ".../mcp" endpoint — the default ("/mcp") would double up into ".../mcp/mcp".
#
# streamable_http_app() also creates the MCP session manager lazily, and that
# manager needs its own async context started — FastAPI doesn't propagate
# lifespan into mounted sub-apps automatically, so without the lifespan
# wiring below, a request here fails with "Task group is not initialized.
# Make sure to use run()." Verified by reproducing that exact failure first.
_mcp_app = mcp.streamable_http_app(streamable_http_path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Sinolume Internal Analyst Companion API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", _mcp_app)

_bearer = HTTPBearer()


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> int:
    try:
        return auth.decode_access_token(credentials.credentials)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


class LoginRequest(BaseModel):
    username: str
    password: str


class IdentifyRequest(BaseModel):
    snippet: str


class AskRequest(BaseModel):
    question: str
    source_document: str
    session_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(req: LoginRequest):
    try:
        user = auth.authenticate_user(req.username, req.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return {"access_token": auth.create_access_token(user["id"])}


@app.post("/identify")
def identify(req: IdentifyRequest, user_id: int = Depends(get_current_user_id)):
    return identify_source(req.snippet)


@app.post("/ask")
def ask(req: AskRequest, user_id: int = Depends(get_current_user_id)):
    return conversations.ask_and_persist(user_id, req.question, req.source_document, req.session_id)


@app.get("/conversations")
def conversations_list(user_id: int = Depends(get_current_user_id)):
    return conversations.list_threads(user_id)


@app.get("/conversations/{session_id}")
def conversation_detail(session_id: str, user_id: int = Depends(get_current_user_id)):
    thread = conversations.get_thread(user_id, session_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    thread["messages"] = conversations.get_messages(session_id)
    return thread


@app.delete("/conversations/{session_id}")
def conversation_delete(session_id: str, user_id: int = Depends(get_current_user_id)):
    deleted = conversations.delete_thread(user_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}
