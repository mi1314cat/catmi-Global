#!/usr/bin/env python3
"""news.config — 管道配置（全部无秘密；秘密走 env.local 由运维注入）"""
import os, pathlib, sys

def _home_default():
    return pathlib.Path(os.environ.get("NEWS_HOME", os.path.expanduser("~/news-project")))

def load_env_file(p: pathlib.Path):
    """KEY=VALUE（# 注释）；绝不打印值"""
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

HOME = _home_default()
DATA = HOME / "news-data"
DB_PATH = DATA / "database" / "news.db"
IMAGES = DATA / "images"
CACHE = DATA / "cache"          # 原始页面 gz 缓存（72h 滚动）
LOGS = DATA / "logs"
_env = load_env_file(HOME / "env.local")

def get(key, default=""):
    return _env.get(key, os.environ.get(key, default))

# --- 网络 ---
UA = get("COLLECTOR_UA", "NewsResearchBot/0.1 (personal research; +https://<你的域名>)")
HTTP_TIMEOUT = float(get("HTTP_TIMEOUT", "20"))
HTTP_RETRIES = int(get("HTTP_RETRIES", "3"))
RETRY_DELAYS = (2.0, 5.0)                       # 指数退避前两级；落库重试用 crawl_tasks.next_attempt_at
DOMAIN_DELAY = float(get("DOMAIN_DELAY", "1.2"))  # 同域礼貌间隔(秒)
MAX_ITEMS_PER_FEED = int(get("MAX_ITEMS_PER_FEED", "40"))

# --- 采集节奏 ---
SCAN_BATCH = int(get("SCAN_BATCH", "16"))       # 每轮 scan 处理的源数（cron 分片）
FETCH_BATCH = int(get("FETCH_BATCH", "30"))     # 每轮正文抓取篇数
IMAGE_BATCH = int(get("IMAGE_BATCH", "10"))
SOURCE_DISABLE_AFTER = int(get("SOURCE_DISABLE_AFTER", "5"))  # 连续失败 N 次停用
TASK_RETRY_BACKOFF = (3600, 4 * 3600, 12 * 3600)              # 落库重试: 1h/4h/12h
TASK_MAX_ATTEMPTS = 3

# --- 提取 ---
EXTRACT_MIN_CHARS = int(get("EXTRACT_MIN_CHARS", "200"))
CONTENT_MAX_CHARS = int(get("CONTENT_MAX_CHARS", "200000"))
IMAGE_MAX_BYTES = int(get("IMAGE_MAX_BYTES", str(8 * 1024 * 1024)))
IMAGE_MIN_BYTES = int(get("IMAGE_MIN_BYTES", "3000"))

# --- 存储/保留（小时; 可被 env.local 覆盖） ---
RETENTION_CONTENT_H = int(get("RETENTION_CONTENT_H", "72"))    # 正文+图片 72h 滚动
RETENTION_IMAGES_H = int(get("RETENTION_IMAGES_H", "72"))
RETENTION_RAW_H = int(get("RETENTION_RAW_H", "24"))            # 原始页面缓存
RETENTION_METADATA_D = int(get("RETENTION_METADATA_D", "30"))  # 元数据
RETENTION_STORY_D = int(get("RETENTION_STORY_D", "90"))        # story 长期层
RETENTION_ERRORS_D = int(get("RETENTION_ERRORS_D", "14"))

# --- 磁盘保护（占配额百分比; 配额默认 3.0G） ---
QUOTA_BYTES = float(get("QUOTA_BYTES", str(3.0 * 1024**3)))
DISK_WARN = int(get("DISK_WARN", "50"))
DISK_HIGH = int(get("DISK_HIGH", "70"))
DISK_EMERGENCY = int(get("DISK_EMERGENCY", "85"))

# --- AI（可插拔, 核心零依赖; 无 key 时全部跳过） ---
AI_BASE_URL = get("AI_BASE_URL", "")
AI_API_KEY = get("AI_API_KEY", "")              # 仅内存使用, 永不落盘/日志
AI_MODEL = get("AI_MODEL", "")

def ensure_dirs():
    for p in (DATA, DATA / "database", IMAGES, CACHE, LOGS):
        p.mkdir(parents=True, exist_ok=True)

def disk_usage_pct(used_bytes: float) -> float:
    return round(100.0 * used_bytes / QUOTA_BYTES, 2)

def disk_level(pct: float) -> str:
    if pct >= DISK_EMERGENCY: return "emergency"
    if pct >= DISK_HIGH: return "high"
    if pct >= DISK_WARN: return "warn"
    return "normal"
