# Context for a fresh Claude session starting in this folder

This file exists because this project was scoped out in a long conversation
that happened in a **different** project folder (`d:\firstclass-demo`), whose
memory/context does not carry over here automatically. Read this file first.

## What this project is

An internal-facing companion tool to the "Sinolytics RAG Demo" project at
`d:\firstclass-demo` — read that project's `README.md`, `docs/PRD_v1.1.md`,
`docs/TechSpec_v1.1.md`, `docs/PRD_v1.2.md`, and `docs/TechSpec_v1.2.md` for
full context on the existing, client-facing product before starting.

The existing project is a client-facing RAG chatbot for a fictional China
strategy advisory firm ("Sinolytics"). This new project models a companion
tool **for the firm's own internal analysts** rather than clients — like the
client product, it's ultimately a portfolio piece for an interview (Working
Student – Data and AI Application role), not something meant to run against
a real company's real data. It does not need production-grade completeness;
it needs its core mechanic to genuinely work and be demonstrable.

Core idea (as scoped with the user so far, subject to refinement): the firm's
analysts have a large library of internal reports. An analyst can:
1. Upload an image (a photo/screenshot of a report page, or a chart cut out
   of a report) or paste a snippet of text.
2. The tool identifies **which specific internal document** that image/text
   came from.
3. The analyst can then ask follow-up questions scoped to that identified
   document.

Technical notes already discussed (not yet decided/built):
- Text-snippet matching can reuse the existing project's embedding-based
  `hybrid_search` approach directly — a real excerpt should score much
  higher than a topically-similar-but-different query, so a similarity
  threshold can distinguish "this IS the source" from "this is just related."
- Image matching was discussed specifically for **charts** (not tables) —
  charts don't have OCR-friendly row/column structure. Two viable
  approaches, likely combined: (a) OCR whatever text IS on the chart (title,
  axis labels, legend) and text-match that; (b) have a vision-capable model
  write a one-sentence description of the chart and semantically match that
  description against document content.
- The existing project's document ingestion (`embed_and_store.py`) only
  handles plain `.txt` files and never retains original images/charts —
  this new project's own ingestion pipeline will need to be designed
  differently to retain chart images (or their captions/OCR'd text) at
  index time, or there's nothing for an uploaded image to match against.
- The user plans to download a short, real sample file (a few pages, mostly
  charts) from Sinolytics' actual public website to use as test material —
  it should end up in this folder once ready.

**Important, explicit user decision**: this project should be built using
**MCP** (Model Context Protocol) — the user specifically wants this because
the job description they're interviewing for mentions it, and an
internal-only tool (no need for a public web UI) is a good natural fit for
an MCP server usable directly from Claude Desktop/Claude Code. Do not
re-litigate build-vs-MCP as an open question — research and propose *how*
to structure it as (or around) an MCP server, the same way the
`doc-coauthoring` skill was found and installed as a project-level skill in
the other project. Look for a well-regarded skill/workflow for *building*
MCP servers or agent tooling, install it project-level in **this** folder
(not globally), and use it to guide the build.

## User's working preferences (carried over, apply here too)

- **PRD before code, requirements only**: write a requirements-only PRD
  first (no technical/implementation detail in it), using the
  `doc-coauthoring` skill's stage-by-stage workflow, by default and
  unprompted — this user has explicitly asked for this to be the standing
  approach for every doc/spec in their projects, not just when asked.
- **Stop at technical decision points**: when writing a technical spec or
  making an architecture/library choice, ask the user before deciding —
  don't pick silently and move on.
- **No technical background**: the user is not a developer. Explain jargon
  in plain language (大白话). They reason well about tradeoffs once
  explained in plain terms — the gap is vocabulary/familiarity, not
  judgment.
- **Confirm before each deployment-related action**: don't chain multiple
  deploy steps on one approval — check in before each one.
- **Never commit/push `.env` or other secrets**; get explicit confirmation
  before any push in general.
- **Converse in Chinese** in chat turns (the user reads/writes Chinese
  throughout). English is fine for the actual document artifacts
  themselves (e.g. producing both a `.md` and `.en.md` version), and for
  code/config — it's specifically the conversational turns that should
  default to Chinese.

## Suggested first step in the new session

Read the referenced files in `d:\firstclass-demo` for product context, then
pick up the doc-coauthoring workflow for this project's own PRD — the user
already has real opinions about scope (see "Core idea" above) so Stage 1
context-gathering shouldn't need to start from zero.
