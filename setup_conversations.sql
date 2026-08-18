-- Run this once in the Supabase SQL Editor (same project as setup_supabase.sql),
-- to add conversation history persistence. No per-user scoping yet — this
-- is single-user for tonight's demo; a `user_id` column can be added later
-- without restructuring anything here.

create table if not exists conversation_threads (
  session_id uuid primary key default gen_random_uuid(),
  title text not null,
  source_document text not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists conversation_messages (
  id bigint generated always as identity primary key,
  session_id uuid not null references conversation_threads(session_id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now()
);

create index if not exists conversation_messages_session_idx
  on conversation_messages (session_id, created_at);
