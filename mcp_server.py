"""MCP server: exposes the same core mechanic (document_id.py +
conversations.py) directly to an MCP client (Claude Desktop, Claude Code),
so an analyst can identify a document and ask about it from a normal chat —
no web page involved. Runs alongside, not instead of, the FastAPI+web path
in api.py/app.html — both call the same underlying functions.

Auth: every tool that touches conversation memory takes an explicit `token`
argument (from `login`) rather than relying on transport-level headers —
stdio (local Claude Desktop/Code) has no HTTP headers to hook into, and
using the same token-argument approach for both stdio and the remote
streamable-http deployment (see api.py) means one auth mechanism, not two.
"""

import auth
import conversations
from document_id import identify_source

from mcp.server import MCPServer

mcp = MCPServer(
    name="sinolume-internal-document-finder",
    instructions=(
        "Identifies which internal Sinolume document a pasted text snippet "
        "came from, then answers follow-up questions scoped to that document. "
        "Call login first to get a token — ask_document and list_conversations "
        "require one. Always call identify_document before ask_document — "
        "never guess a source_document without a matched result."
    ),
)


def _require_user(token: str) -> int:
    try:
        return auth.decode_access_token(token)
    except auth.AuthError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def login(username: str, password: str) -> dict:
    """Log in with a whitelisted account. Returns a token (valid 30 days)
    that ask_document and list_conversations require. There is no
    self-service signup — an account must already exist."""
    try:
        user = auth.authenticate_user(username, password)
    except auth.AuthError as exc:
        return {"success": False, "error": str(exc)}
    token = auth.create_access_token(user["id"])
    return {"success": True, "token": token}


@mcp.tool()
def identify_document(snippet: str) -> dict:
    """Identify which internal document a pasted text snippet came from.

    Returns matched=True with a source_document if the snippet is genuinely
    excerpted from a document in the corpus, or matched=False if it's only
    topically related (or unrelated) — never guess a document when unsure.
    Doesn't require a token — identifying a source isn't tied to any one
    account's conversation history.
    """
    return identify_source(snippet)


@mcp.tool()
def ask_document(
    token: str, question: str, source_document: str, session_id: str | None = None
) -> dict:
    """Ask a question scoped strictly to one identified document.

    Requires a token from login. source_document must come from a prior
    identify_document call that returned matched=True. Pass the session_id
    from a previous ask_document call to continue that same conversation
    with memory of earlier turns; omit it to start a new thread.
    """
    user_id = _require_user(token)
    return conversations.ask_and_persist(user_id, question, source_document, session_id)


@mcp.tool()
def list_conversations(token: str) -> list:
    """List the logged-in account's past conversation threads (title, source
    document, last updated), most recently updated first. Requires a token
    from login — only returns that account's own threads."""
    user_id = _require_user(token)
    return conversations.list_threads(user_id)


if __name__ == "__main__":
    mcp.run()
