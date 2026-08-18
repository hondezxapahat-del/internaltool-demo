"""MCP server: exposes the same core mechanic (document_id.py +
conversations.py) directly to an MCP client (Claude Desktop, Claude Code),
so an analyst can identify a document and ask about it from a normal chat —
no web page involved. Runs alongside, not instead of, the FastAPI+web path
in api.py/app.html — both call the same underlying functions.
"""

from mcp.server import MCPServer

import conversations
from document_id import identify_source

mcp = MCPServer(
    name="sinolytics-internal-document-finder",
    instructions=(
        "Identifies which internal Sinolytics document a pasted text snippet "
        "came from, then answers follow-up questions scoped to that document. "
        "Always call identify_document first — never guess a source_document "
        "for ask_document without a matched result from identify_document."
    ),
)


@mcp.tool()
def identify_document(snippet: str) -> dict:
    """Identify which internal document a pasted text snippet came from.

    Returns matched=True with a source_document if the snippet is genuinely
    excerpted from a document in the corpus, or matched=False if it's only
    topically related (or unrelated) — never guess a document when unsure.
    """
    return identify_source(snippet)


@mcp.tool()
def ask_document(question: str, source_document: str, session_id: str | None = None) -> dict:
    """Ask a question scoped strictly to one identified document.

    source_document must come from a prior identify_document call that
    returned matched=True. Pass the session_id from a previous ask_document
    call to continue that same conversation with memory of earlier turns;
    omit it to start a new conversation thread.
    """
    return conversations.ask_and_persist(question, source_document, session_id)


@mcp.tool()
def list_conversations() -> list:
    """List past conversation threads (title, source document, last updated),
    most recently updated first."""
    return conversations.list_threads()


if __name__ == "__main__":
    mcp.run()
