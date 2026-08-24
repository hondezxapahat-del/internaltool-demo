# Sinolume Internal Document Finder

An internal-facing companion tool to the [Sinolume RAG Demo](https://github.com/hondezxapahat-del/firstclass-demo) client-facing project — an analyst pastes a text snippet, the tool identifies exactly which internal report it came from, then answers follow-up questions scoped strictly to that document, with full server-side conversation memory. Exposed both as a normal web app and as an [MCP](https://modelcontextprotocol.io) server, so the same capability is usable directly from an MCP client (Claude Desktop, Claude Code) with no web page involved.

## Status

**Built and deployed**: text-snippet source identification, scoped follow-up Q&A with persistent conversation memory, web frontend, MCP server. See [What's built](#whats-built) below.

**Not yet built**: account/login, chart/image sourcing, a candidate-list fallback for uncertain matches, topic search across the corpus, and groundwork for scaling past a handful of documents. These are specified in [docs/PRD_v1.2.md](docs/PRD_v1.2.md) / [docs/TechSpec_v1.2.md](docs/TechSpec_v1.2.md) but not implemented — don't take their presence in this repo's `docs/` folder as evidence they're live.

## Background

This project was built as a companion to the Sinolume RAG Demo — also a technical proof-of-concept for the **Working Student – Data and AI Application** role, this time modeling a tool for the firm's own internal analysts rather than external clients. Analysts routinely receive a forwarded screenshot, a chart cut from a report, or a bare text snippet without knowing which of the firm's own reports it's from — this tool answers that question directly, then lets the analyst dig into that specific document.

The two projects share a corpus (a subset of the client-facing project's briefs/whitepaper) and a visual style, but are otherwise fully independent — no shared backend, accounts, or logic.

## Tech Stack

- **Python** — backend logic, retrieval, ingestion
- **FastAPI** — REST API serving the web frontend
- **MCP Python SDK** (`mcp`) — a second interface exposing the same core logic directly to MCP clients
- **OpenAI API** — `text-embedding-3-small` for embeddings, `gpt-4o-mini` for reranking and answer generation
- **Supabase (Postgres + pgvector)** — vector storage, cosine-similarity search, full-text keyword search, conversation persistence
- **HTML / CSS / JavaScript** — vanilla frontend, no framework
- **Deployment** — Render (API), Vercel (static frontend)

## Architecture

Core logic (`document_id.py`, `conversations.py`) is kept independent of any interface — the same principle as the client-facing project's `tools.py` being independent of its LangChain wiring. Two thin interface layers call the same functions:

```
                         ┌─────────────────────┐
                         │  document_id.py      │  ← identify + scoped Q&A
                         │  conversations.py     │  ← thread/message persistence
                         └─────────┬────────────┘
                                   │
                  ┌────────────────┴────────────────┐
                  │                                  │
           api.py (FastAPI)                  mcp_server.py (MCP)
                  │                                  │
             app.html (web)              Claude Desktop / Claude Code
```

A request flows: paste snippet → `identify_source()` → literal-text match (a real excerpt shares one long contiguous run with its source doc) → falls back to embedding-similarity match if no strong literal overlap → once a document is identified, `answer_within_document()` reranks every chunk belonging to that document against the (context-aware) question, drops anything below a relevance floor, and answers strictly from what's left.

## Feature Modules

### 1. Ingestion (`embed_and_store.py`)

Reads `.txt` files from `docs/`, splits them into sentence-aware chunks (~500 characters), embeds each with OpenAI, and stores them in Supabase's `documents` table — which, unlike the client-facing project's table of the same name, also records `source_document` per chunk. That column is the whole reason this project can report *which* document matched, not just answer from a pooled corpus.

### 2. Retrieval (`retrieval.py`)

Same hybrid-search shape as the client-facing project: `match_documents` (pgvector cosine similarity) + `keyword_search` (Postgres full-text) merged into one deduped candidate pool, then `rerank()` scores every candidate's relevance in a single batched LLM call.

### 3. Source identification (`document_id.py`)

- `identify_source(snippet)` — two-gate check: a literal contiguous-text-overlap ratio against each corpus document (`LITERAL_MATCH_THRESHOLD = 0.6`) catches a real pasted excerpt with near-certainty; an embedding-similarity fallback (`EMBEDDING_MATCH_THRESHOLD = 0.83`) catches paraphrased/OCR'd excerpts. Below both thresholds, the snippet is reported as unmatched rather than forced onto the nearest topically-related document — verified against real test cases (an actual excerpt, a topically-related-but-invented sentence, and an unrelated sentence) during development.
- `answer_within_document(question, source_document, conversation_history)` — reranks every chunk belonging to the identified document against a context-aware version of the question (folding in recent conversation turns so a bare follow-up like "what about that?" still retrieves correctly), answers strictly from chunks that clear a relevance floor, then runs a second LLM pass that audits its own draft against the actual retrieved context — catching vague quantifiers ("various", "significant") standing in for a number the source actually gives, and content that was clearly relevant but got left out.
- The number of chunks fed into the answer prompt scales with how large the source document is (`min(20, max(5, chunk_count // 4))`) rather than a fixed count — a fixed small count was the root cause of answers reading as generic on the corpus's largest document.

### 4. Conversation memory (`conversations.py`)

`ask_and_persist()` is the single write path both interfaces call: creates a new thread (title = first question, truncated) or continues an existing one by `session_id`, persists both turns, and updates the thread's timestamp. Backed by two Supabase tables (`conversation_threads`, `conversation_messages`) — no per-user scoping yet (see Status above).

### 5. API layer (`api.py`)

`POST /identify`, `POST /ask`, `GET /conversations`, `GET /conversations/{id}`, `DELETE /conversations/{id}`, `GET /health`. No auth yet — single-user for now.

### 6. MCP server (`mcp_server.py`)

Exposes three tools via the official MCP Python SDK's high-level `MCPServer` API: `identify_document`, `ask_document` (accepts an optional `session_id` to continue a thread), `list_conversations`. The server's own `instructions` field tells a connecting AI client to always call `identify_document` before `ask_document` — never guess a `source_document`. Configured project-locally via `.mcp.json`, so Claude Code picks it up automatically; see that file for the equivalent Claude Desktop config.

### 7. Frontend

- `index.html` — landing page, links into the tool.
- `app.html` — the actual tool: paste-a-snippet card, then (once matched) a chat interface with a sidebar of past conversations, new-chat, delete, and a composer — visually matching the client-facing project's style (white background, black text, `#a4161a` red accent) but with internal-workbench copy rather than client-facing marketing copy.

## Technical Challenges & Solutions

- **Distinguishing "this is the source" from "this is just related"** — a pure embedding-similarity threshold is fragile on its own (a topically-similar-but-different passage can score close to a real excerpt). Adding a literal contiguous-text-overlap check as the first gate, with embedding similarity only as a fallback for paraphrased/non-literal excerpts, made this reliable enough to verify against real test cases rather than tuning a single number by feel.
- **Short-snippet false positives** — a short string like "the report" can trivially appear as a substring of an unrelated document by chance, sending the literal-match ratio to 1.0 for the wrong reason. Below `MIN_SNIPPET_LENGTH_FOR_LITERAL = 30` characters, literal matching is skipped and the embedding check is used instead.
- **Generic-reading answers on the largest document** — traced to a fixed, small chunk count being fed into every answer regardless of document size; fixed by scaling chunk count with document size and adding a self-check/refine pass (see §3 above). This is a real, verified fix, not a prompt tweak taken on faith — before/after tested against the corpus's largest document.
- **Reused table schema, one real difference from the client-facing project** — the client-facing project's `documents` table never recorded which file a chunk came from (it didn't need to, since it answers from the whole pooled corpus). This project's `documents` table adds `source_document` — the one schema change needed to make "which document is this from" answerable at all.
- **Core logic decoupled from both interfaces** — `document_id.py`/`conversations.py` know nothing about FastAPI or MCP; both `api.py` and `mcp_server.py` are thin wrappers calling the same functions, so a conversation started from one interface behaves identically to one started from the other.
- **`.env` loading assumed the working directory** — `load_dotenv()` with no path only searches upward from the current working directory, which is fine when Claude Code sets the project directory as cwd, but not guaranteed for other launchers (e.g. Claude Desktop's `mcpServers` config, which launches by absolute path). Fixed to load `.env` by an explicit path relative to the script itself; verified by actually launching from a different working directory.

## Data Used

Corpus: a subset of the client-facing project's material — 3 short China AI/tech market briefs and 1 export-controls whitepaper, fictionalized under the same "Sinolume" persona as the client-facing project (see `docs/`). Same caveat as the client-facing project: this is demo material for a portfolio piece, not a live production dataset.

## How to Run

1. Clone the repository and `cd` into it.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with:
   ```
   OPENAI_API_KEY=...
   SUPABASE_URL=...
   SUPABASE_SERVICE_ROLE_KEY=...
   ```
4. In the Supabase SQL editor, run `setup_supabase.sql` then `setup_conversations.sql` once, to create the `documents` table + retrieval functions and the conversation-persistence tables.
5. Embed and store the corpus:
   ```bash
   python embed_and_store.py
   ```
6. Start the API:
   ```bash
   uvicorn api:app --reload
   ```
7. Open `index.html` in a browser, click through to the tool, paste a real excerpt from one of the `docs/*.txt` files, and try a follow-up question.
8. (Optional) Run the MCP server directly: `python mcp_server.py` — or open this project in Claude Code, which picks it up automatically via `.mcp.json`.

## Live Deployment

- Frontend: https://internaltool-demo.vercel.app
- API: https://internaltool-demo.onrender.com (free tier — sleeps after 15 minutes idle, first request after that takes 30-60s to wake up)

## Future Directions

See [docs/PRD_v1.2.md](docs/PRD_v1.2.md) for the full requirements and [docs/TechSpec_v1.2.md](docs/TechSpec_v1.2.md) for the technical design — in priority order: username/password + whitelist login, chart/image source identification, a candidate-list fallback when match confidence is uncertain, topic search across the whole corpus, and groundwork for retrieval quality at a much larger corpus size (contextual chunk embedding, token-based chunking, a tunable candidate pool).
