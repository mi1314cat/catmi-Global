#!/usr/bin/env python3
"""news.db — SQLite 连接/WAL/初始化/通用助手（无任何秘密）"""
import hashlib, json, pathlib, sqlite3
from datetime import datetime, timezone, timedelta

from . import config

SCHEMA = (pathlib.Path(__file__).resolve().parent / "schema.sql").read_text()
SCHEMA_VERSION = 1

def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def iso_ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_schema(con: sqlite3.Connection):
    con.executescript(SCHEMA)
    # 迁移: 补充历史库缺失列
    arts = {r[1] for r in con.execute("PRAGMA table_info(articles)")}
    for col in ("summary_text TEXT", "dupe_of INTEGER"):
        name = col.split()[0]
        if name not in arts:
            con.execute(f"ALTER TABLE articles ADD COLUMN {col}")
    srcs = {r[1] for r in con.execute("PRAGMA table_info(sources)")}
    if "adapter" not in srcs:
        con.execute("ALTER TABLE sources ADD COLUMN adapter TEXT")
    con.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))
    con.commit()

def meta_get(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def meta_set(con, key, value):
    con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    con.commit()

def log_error(con, source_id, url, stage, kind, detail):
    con.execute("INSERT INTO crawl_errors(source_id,url,stage,kind,detail,at) VALUES(?,?,?,?,?,?)",
                (source_id, url, stage, kind, str(detail)[:500], utcnow()))

def jload(s, default=None):
    try: return json.loads(s) if s else default
    except Exception: return default
