"""migrate_ext — Source Intelligence 扩展 schema（幂等, 短事务, WAL 安全）"""
from . import db as dbm

def _has_col(con, table, col):
    return any(r[1] == col for r in con.execute(f"PRAGMA table_info({table})"))

def ensure(con):
    notes = []
    for col, ddl in (("source_type", "TEXT"), ("tier", "TEXT"), ("quality_score", "INTEGER"),
                     ("verification_status", "TEXT")):
        if not _has_col(con, "sources", col):
            con.execute(f"ALTER TABLE sources ADD COLUMN {col} {ddl}"); notes.append(f"sources.{col}")
    for col, ddl in (("importance", "TEXT"), ("importance_reason", "TEXT"),
                     ("ai_enhanced", "INTEGER"), ("ai_model", "TEXT"), ("ai_prompt_version", "TEXT"),
                     ("ai_at", "TEXT"), ("ai_summary", "TEXT"), ("ai_entities", "TEXT"),
                     ("ai_timeline", "TEXT"),
                     ("fact_status", "TEXT"), ("fact_status_updated_at", "TEXT"),
                     ("independent_source_count", "INTEGER")):
        if not _has_col(con, "stories", col):
            con.execute(f"ALTER TABLE stories ADD COLUMN {col} {ddl}"); notes.append(f"stories.{col}")
    con.execute("""CREATE TABLE IF NOT EXISTS candidate_sources(
        id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, kind TEXT, feed_url TEXT, site_url TEXT,
        category TEXT, language TEXT, country TEXT, source_type TEXT, tier TEXT, quality_score INTEGER,
        verification_status TEXT DEFAULT 'pending', discovered_via TEXT, probe_json TEXT, notes TEXT,
        created_at TEXT, updated_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS event_evidence(
        id INTEGER PRIMARY KEY, story_id INTEGER, article_id INTEGER, domain TEXT,
        source_type TEXT, tier TEXT, is_original INTEGER, at TEXT,
        UNIQUE(story_id, article_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS ai_queue(
        id INTEGER PRIMARY KEY, story_id INTEGER, task_type TEXT, priority INTEGER, status TEXT DEFAULT 'pending',
        attempts INTEGER DEFAULT 0, last_error TEXT, created_at TEXT, processed_at TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_aiq ON ai_queue(status, priority DESC)")
    con.execute("""CREATE TABLE IF NOT EXISTS ai_cache(
        id INTEGER PRIMARY KEY, input_hash TEXT, task_type TEXT, prompt_version TEXT, model TEXT,
        response TEXT, created_at TEXT, UNIQUE(input_hash, task_type, prompt_version, model))""")
    con.execute("""CREATE TABLE IF NOT EXISTS story_fact_history(
        id INTEGER PRIMARY KEY, story_id INTEGER, fact_status TEXT, reason TEXT, at TEXT)""")
    con.commit()
    return notes
