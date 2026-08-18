-- Run this once in the new Supabase project's SQL Editor, top to bottom,
-- before running the ingestion script.

-- 1. Enable the pgvector extension (for embedding similarity search).
create extension if not exists vector;

-- 2. The chunk table. Unlike the client-facing project's `documents` table,
--    this one tracks which source file each chunk came from — the new
--    project's whole point is reporting *which document* matched, not just
--    answering from an undifferentiated pool.
create table if not exists documents (
  id bigint generated always as identity primary key,
  content text not null,
  embedding vector(1536),
  source_document text not null,
  created_at timestamptz default now()
);

-- 3. Full-text index, backing keyword_search below.
create index if not exists documents_content_fts_idx
  on documents
  using gin (to_tsvector('english', content));

-- 4. Vector similarity search — same shape as the client-facing project's
--    match_documents.sql, plus source_document in the return columns.
create or replace function match_documents (
  query_embedding vector(1536),
  match_count int default 5
)
returns table (
  id bigint,
  content text,
  source_document text,
  similarity float
)
language sql stable
as $$
  select
    documents.id,
    documents.content,
    documents.source_document,
    1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  order by documents.embedding <=> query_embedding
  limit match_count;
$$;

-- 5. Keyword search — same shape as the client-facing project's
--    keyword_search.sql, plus source_document in the return columns.
create or replace function keyword_search (
  query_text text,
  match_count int default 5
)
returns table (
  id bigint,
  content text,
  source_document text,
  rank float
)
language sql stable
as $$
  select
    documents.id,
    documents.content,
    documents.source_document,
    ts_rank(to_tsvector('english', documents.content), plainto_tsquery('english', query_text)) as rank
  from documents
  where to_tsvector('english', documents.content) @@ plainto_tsquery('english', query_text)
  order by rank desc
  limit match_count;
$$;
