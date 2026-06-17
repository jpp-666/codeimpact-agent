CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  repo TEXT NOT NULL,
  path TEXT NOT NULL,
  chunk_type TEXT NOT NULL,
  symbol TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  content TEXT NOT NULL,
  snippet TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
USING fts5(repo, path, chunk_type, symbol, content);
