#!/bin/sh
# ai-worker.sh — AI 队列快速通道（*/5 分钟; 无任务立即退出, 不常驻）
set -u
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJ=$(dirname "$SCRIPT_DIR")
cd "$PROJ" || exit 1   # [R6-P1-S3] cron cwd=$HOME; python -c 用 cwd 作 sys.path[0]
exec "$PROJ/venv/bin/python" -c '
from news import db as dbm
from news import ai
con = dbm.connect(); con.execute("PRAGMA busy_timeout=15000")
ai.enqueue(con)
r = ai.worker(con)
print(r, flush=True)
con.close()'
