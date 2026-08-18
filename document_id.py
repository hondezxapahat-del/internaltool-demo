"""Core mechanic: identify which internal document a pasted text snippet came
from, then answer follow-up questions scoped to that one document.

Kept independent of any interface (FastAPI, MCP) — same principle as the
client-facing project's tools.py being independent of LangChain routing.
Both the web backend and the MCP server just call these functions.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path

from retrieval import hybrid_search, openai_client, rerank, supabase

DOCS_DIR = Path(__file__).parent / "docs"
ANSWER_MODEL = "gpt-4o-mini"

# A pasted excerpt that really is from a document should share one long
# contiguous run of text with it (near 1.0 for an exact paste; real-world
# whitespace/line-break differences pull this down some). A snippet that's
# merely on the same topic won't share a long contiguous run at all, even if
# individual words overlap — so this catches "this IS the source" far more
# reliably than similarity alone.
LITERAL_MATCH_THRESHOLD = 0.6

# Fallback for snippets that are genuinely from a document but paraphrased,
# OCR'd, or otherwise not a clean literal substring. text-embedding-3-small
# cosine similarity for a real excerpt of the same passage runs noticeably
# higher than for a merely-related passage on the same topic — this is a
# conservative cut set above that gap, not a validated statistical bound.
EMBEDDING_MATCH_THRESHOLD = 0.83

# Below this rerank score (0-10), a chunk is considered too weakly related
# to the follow-up question to belong in the answer prompt.
MIN_CONTEXT_SCORE = 5.0

# A short snippet ("test", "the report") can trivially appear as a
# substring of some unrelated document purely by chance, which would send
# the literal-match ratio to 1.0 for the wrong reason. Below this length,
# literal matching is too unreliable to trust — fall straight through to
# the embedding-based check instead.
MIN_SNIPPET_LENGTH_FOR_LITERAL = 30

NO_FABRICATION_RULE = (
    "Only state a specific year, date, number, or named entity (company, "
    "agency, person) if it appears explicitly in the provided context. If "
    "the context doesn't name one, do not invent or infer it."
)

SPECIFICITY_RULE = (
    "Prefer the document's own concrete figures, dates, and named entities "
    "over vague quantifiers — if the context gives a specific number, cite "
    "it; don't summarize it away as 'various', 'several', or 'significant' "
    "unless the context itself only speaks in those vague terms. Where the "
    "context distinguishes a plain fact from the author's own judgment, "
    "prediction, or recommendation, keep that distinction visible in the "
    "answer rather than flattening both into one voice."
)


def _normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _find_literal_match(snippet):
    """Longest contiguous run the snippet shares with each source .txt file,
    as a fraction of the snippet's own length. Returns (filename, ratio) for
    the best match, or (None, 0.0) if there are no corpus files."""
    normalized_snippet = _normalize(snippet)
    if not normalized_snippet:
        return None, 0.0

    best_name, best_ratio = None, 0.0
    for path in sorted(DOCS_DIR.glob("*.txt")):
        normalized_doc = _normalize(path.read_text(encoding="utf-8"))
        matcher = SequenceMatcher(None, normalized_snippet, normalized_doc, autojunk=False)
        match = matcher.find_longest_match(0, len(normalized_snippet), 0, len(normalized_doc))
        ratio = match.size / len(normalized_snippet)
        if ratio > best_ratio:
            best_name, best_ratio = path.name, ratio

    return best_name, best_ratio


def identify_source(snippet):
    """Decide whether `snippet` is actually excerpted from one of the corpus
    documents, as opposed to merely being on a related topic.

    Returns one of:
      {"matched": True, "source_document": ..., "method": "literal"|"embedding", "confidence": float}
      {"matched": False, "closest_document": ..., "closest_similarity": float}  (if any candidate was found)
      {"matched": False}  (nothing in the corpus was even close)
    """
    literal_name, literal_ratio = (None, 0.0)
    if len(_normalize(snippet)) >= MIN_SNIPPET_LENGTH_FOR_LITERAL:
        literal_name, literal_ratio = _find_literal_match(snippet)
    if literal_ratio >= LITERAL_MATCH_THRESHOLD:
        return {
            "matched": True,
            "source_document": literal_name,
            "method": "literal",
            "confidence": round(literal_ratio, 3),
        }

    candidates = hybrid_search(snippet, match_count=5)
    scored = [c for c in candidates if c["similarity"] is not None]
    if not scored:
        return {"matched": False}

    best = max(scored, key=lambda c: c["similarity"])
    if best["similarity"] >= EMBEDDING_MATCH_THRESHOLD:
        return {
            "matched": True,
            "source_document": best["source_document"],
            "method": "embedding",
            "confidence": round(best["similarity"], 3),
        }

    return {
        "matched": False,
        "closest_document": best["source_document"],
        "closest_similarity": round(best["similarity"], 3),
    }


def _get_all_chunks(source_document):
    result = (
        supabase.table("documents")
        .select("id, content, source_document")
        .eq("source_document", source_document)
        .order("id")
        .execute()
    )
    return result.data


def _contextualize_for_rerank(question, conversation_history, max_turns=4):
    """A bare follow-up like 'what did I just ask' or 'what about that' has
    no lexical/semantic overlap with the document itself — reranking it
    alone against document chunks scores everything as irrelevant. Folding
    in the last few turns gives the reranker enough context to recognize
    when a follow-up is actually still about something the document covers."""
    if not conversation_history:
        return question
    recent = conversation_history[-max_turns:]
    recent_text = "\n".join(f"{turn['role']}: {turn['content']}" for turn in recent)
    return f"{recent_text}\nuser: {question}"


def _default_top_n(chunk_count):
    """A fixed top_n=5 is fine for a 5-7 chunk brief but starves a 134-chunk
    whitepaper of coverage on any broad question — this is why answers about
    the whitepaper were reading as generic. Scale with document size instead,
    capped so the rerank/answer prompts don't blow up on huge documents."""
    return min(20, max(5, chunk_count // 4))


def _self_check_and_refine(question, context_text, draft_answer):
    """Second pass: have the model audit its own draft against the actual
    context before it goes out. Catches the two failure modes that make an
    answer read as generic — vague quantifiers standing in for a number the
    context actually gives, and clearly-relevant context that got skipped —
    without the cost of a full separate extraction stage per query."""
    prompt = (
        "You wrote a draft answer for an internal policy analyst, grounded in "
        "the context below. Audit your own draft:\n"
        "1. Does it use vague quantifiers ('various', 'several', 'significant', "
        "'many') anywhere the context actually gives a specific figure or name?\n"
        "2. Does it skip over context that's clearly relevant to the question?\n"
        "3. Does it state anything not actually supported by the context?\n\n"
        "If the draft has any of these problems, rewrite it to fix them. "
        "If it's already accurate and specific, return it unchanged. "
        "Respond with only the final answer text — no preamble, no notes "
        "about what you changed.\n\n"
        f"Context:\n{context_text}\n\nQuestion: {question}\n\nDraft answer:\n{draft_answer}"
    )
    response = openai_client.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def answer_within_document(question, source_document, conversation_history=None, top_n=None):
    """Answer `question` using `source_document`'s content and, when present,
    the conversation so far. Every chunk belonging to the document is
    reranked (the corpus is small enough that this stays one batched LLM
    call) against a context-aware version of the question, and only chunks
    clearing MIN_CONTEXT_SCORE are handed to the answer prompt.

    A first turn with nothing relevant is a real "wrong document" signal and
    is refused. A later turn with nothing *newly* relevant is often just a
    question about the conversation itself ("what did I just ask you?") —
    that should still be answered from conversation_history, not refused."""
    chunks = _get_all_chunks(source_document)
    if not chunks:
        return {
            "answer": f"No content found for {source_document}.",
            "source_document": source_document,
            "used_chunks": [],
        }

    if top_n is None:
        top_n = _default_top_n(len(chunks))

    rerank_query = _contextualize_for_rerank(question, conversation_history)
    reranked = rerank(rerank_query, chunks, top_n=top_n)
    context_chunks = [c for c in reranked if c["relevance_score"] >= MIN_CONTEXT_SCORE]

    if not context_chunks and not conversation_history:
        return {
            "answer": (
                f"Nothing in {source_document} appears relevant enough to answer that "
                "— try rephrasing, or confirm this is really the right document."
            ),
            "source_document": source_document,
            "used_chunks": [],
        }

    context_text = (
        "\n\n".join(c["content"] for c in context_chunks)
        if context_chunks
        else "(no additional passage from the document was relevant to this specific question)"
    )
    history_text = ""
    if conversation_history:
        history_text = "\n\nRecent conversation so far:\n" + "\n".join(
            f"{turn['role']}: {turn['content']}" for turn in conversation_history
        )

    prompt = (
        f"You are answering questions strictly about the document '{source_document}', "
        "for an internal policy analyst at a China strategy advisory firm. "
        "Ground every claim about the document's content in the context below — never pad "
        f"with outside knowledge, and never mention other documents. {NO_FABRICATION_RULE} "
        f"{SPECIFICITY_RULE} "
        "If the question is about the conversation itself (e.g. what was just asked) rather "
        "than the document, answer that truthfully from the conversation history instead.\n\n"
        f"Context from {source_document}:\n{context_text}"
        f"{history_text}\n\nQuestion: {question}"
    )
    response = openai_client.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    draft_answer = response.choices[0].message.content.strip()

    final_answer = (
        _self_check_and_refine(question, context_text, draft_answer)
        if context_chunks
        else draft_answer
    )

    return {
        "answer": final_answer,
        "source_document": source_document,
        "used_chunks": [c["id"] for c in context_chunks],
    }
