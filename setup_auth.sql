-- Run this once in the Supabase SQL Editor (same project as the others).
-- No signup endpoint exists — being a row here IS being on the whitelist
-- (TechSpec_v1.2.md §4.6). Add accounts via create_user.py, not SQL directly
-- (it needs to bcrypt-hash the password).

create table if not exists users (
  id bigint generated always as identity primary key,
  username text not null unique,
  password_hash text not null,
  created_at timestamptz default now()
);

-- Existing test-phase threads have no owner — nullable for now, and treated
-- as orphaned data to be cleared before real multi-user use (TechSpec_v1.2.md §4.6).
alter table conversation_threads
  add column if not exists user_id bigint references users(id) on delete cascade;

create index if not exists conversation_threads_user_idx
  on conversation_threads (user_id);
