-- news.db schema v1 (Phase 1) — SQLite, WAL
-- 命名空间: sources/articles/images/stories/story_articles/tags/article_tags/
--           crawl_tasks/crawl_errors/trending/bookmarks + fts
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'rss',          -- rss|api|sitemap|gnews|gdelt|page
  feed_url TEXT,
  site_url TEXT,
  category TEXT DEFAULT 'general',           -- general|tech|finance|geopolitics|society|video
  language TEXT DEFAULT 'en',
  country TEXT,
  priority REAL DEFAULT 1.0,
  poll_seconds INTEGER DEFAULT 900,
  etag TEXT, last_modified TEXT,
  last_fetch_at TEXT, last_ok_at TEXT,
  consecutive_failures INTEGER DEFAULT 0,
  items_total INTEGER DEFAULT 0,
  disabled INTEGER DEFAULT 0, disabled_reason TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_due ON sources(disabled, last_fetch_at);

CREATE TABLE IF NOT EXISTS articles(
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  url TEXT NOT NULL,
  canonical_url TEXT,
  original_title TEXT, title TEXT, author TEXT, summary_text TEXT,
  published_at TEXT,                          -- ISO8601Z (源提供)
  discovered_at TEXT NOT NULL,
  fetched_at TEXT,
  content TEXT,                               -- 提取正文; 72h 后置 NULL (status=purged)
  raw_path TEXT,
  content_hash TEXT,
  language TEXT, category TEXT,
  story_id INTEGER,
  image_main_url TEXT,
  status TEXT DEFAULT 'discovered',           -- discovered|fetched|extracted|noextract|failed|purged|dupe
  extract_method TEXT, error TEXT,
  dupe_of INTEGER,                            -- Article Dedup: 指向被保留的那篇
  UNIQUE(url)
);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status, discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_disc ON articles(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_id);
CREATE INDEX IF NOT EXISTS idx_articles_canon ON articles(canonical_url);
CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_pub ON articles(published_at DESC);

CREATE TABLE IF NOT EXISTS images(
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL REFERENCES articles(id),
  original_url TEXT NOT NULL,
  local_path TEXT, content_hash TEXT,
  bytes INTEGER, width INTEGER, height INTEGER, mime TEXT,
  main INTEGER DEFAULT 0,
  downloaded_at TEXT, purged_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_images_article ON images(article_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_images_hash ON images(content_hash) WHERE content_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS stories(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL, summary TEXT,
  first_seen TEXT NOT NULL, last_updated TEXT NOT NULL,
  heat REAL DEFAULT 0,
  importance TEXT DEFAULT 'normal',           -- low|normal|high|major
  category TEXT, language TEXT,
  entities TEXT, locations TEXT,              -- JSON 数组 (确定性提取; AI 可增强)
  article_count INTEGER DEFAULT 0, source_count INTEGER DEFAULT 0,
  video_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',               -- active|archived
  fingerprint TEXT
);
CREATE INDEX IF NOT EXISTS idx_stories_upd ON stories(last_updated DESC);
CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status, last_updated DESC);

CREATE TABLE IF NOT EXISTS story_articles(
  story_id INTEGER NOT NULL REFERENCES stories(id),
  article_id INTEGER NOT NULL UNIQUE REFERENCES articles(id),
  method TEXT, score REAL, joined_at TEXT,
  PRIMARY KEY(story_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_sa_story ON story_articles(story_id);

CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT);
CREATE TABLE IF NOT EXISTS article_tags(
  article_id INTEGER NOT NULL REFERENCES articles(id),
  tag_id INTEGER NOT NULL REFERENCES tags(id),
  PRIMARY KEY(article_id, tag_id)
);

CREATE TABLE IF NOT EXISTS crawl_tasks(
  id INTEGER PRIMARY KEY,
  article_id INTEGER REFERENCES articles(id),
  url TEXT NOT NULL,
  kind TEXT NOT NULL,                          -- article|image|feed|api
  state TEXT DEFAULT 'pending',                -- pending|running|done|failed|skipped
  attempts INTEGER DEFAULT 0, next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_state ON crawl_tasks(state, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_tasks_article ON crawl_tasks(article_id);

CREATE TABLE IF NOT EXISTS crawl_errors(
  id INTEGER PRIMARY KEY, source_id INTEGER, url TEXT,
  stage TEXT, kind TEXT, detail TEXT, at TEXT
);
CREATE INDEX IF NOT EXISTS idx_errors_at ON crawl_errors(at DESC);

CREATE TABLE IF NOT EXISTS trending(
  story_id INTEGER PRIMARY KEY REFERENCES stories(id),
  score REAL, window_hours INTEGER, computed_at TEXT
);

CREATE TABLE IF NOT EXISTS bookmarks(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER NOT NULL,
  note TEXT, created_at TEXT,
  UNIQUE(kind, ref_id)
);

-- FTS5: rowid == articles.id / stories.id（purge 时同步删行）
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(title, text);
CREATE VIRTUAL TABLE IF NOT EXISTS stories_fts USING fts5(title, entities, locations);
