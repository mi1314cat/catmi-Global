#!/bin/sh
# run-collector.sh — Serve00 Cron 唯一采集入口（one-shot, 跑完即退）
# 职责: lockf 防重叠 + 采集 + 写状态文件 collector-state.json
# 不做: 常驻、无限循环、绕过平台限制
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJ=$(dirname "$SCRIPT_DIR")
PY="$PROJ/venv/bin/python"
STATE_DIR="$PROJ/news-data/state"
STATE="$STATE_DIR/collector-state.json"
LOG="$PROJ/news-data/logs/cron.log"
LOCK=/tmp/news-run.lock          # 复用现有 lockf 锁（进程死亡即自动释放, 无 stale lock）
mkdir -p "$STATE_DIR" "$(dirname "$LOG")"

iso() { TZ=UTC date -u +%Y-%m-%dT%H:%M:%SZ; }

# 状态文件读写（venv python, 幂等合并字段）
wstate() {
  [ -x "$PY" ] || return 0
  "$PY" - "$STATE" "$@" <<'PYEOF' 2>>"$LOG"
import json, sys
path, patch = sys.argv[1], {}
for kv in sys.argv[2:]:
    k, v = kv.split("=", 1)
    patch[k] = None if v == "null" else (int(v) if v.lstrip("-").isdigit() else v)
try:
    st = json.load(open(path))
except Exception:
    st = {}
st.update(patch)
json.dump(st, open(path, "w"), indent=1, ensure_ascii=False)
PYEOF
}

SUBCMD="${1:-run}"
T0=$(date +%s)
wstate last_started_at="$(iso)" last_subcmd="$SUBCMD" last_status=running last_error=null

lockf -t 0 "$LOCK" /bin/sh -c "cd '$PROJ' && exec '$PY' -m news.newsctl '$SUBCMD'" >>"$LOG" 2>&1
RC=$?
DUR=$(( $(date +%s) - T0 ))

if [ "$RC" -eq 75 ]; then
  # 已有一轮在跑（重叠）→ 跳过, 不改成功/失败状态
  echo "$(iso) skip: previous collector still holding lock" >>"$LOG"
  wstate last_skipped_overlap_at="$(iso)" last_finished_at="$(iso)"
  exit 0
fi

if [ "$RC" -eq 0 ]; then
  wstate last_finished_at="$(iso)" last_success_at="$(iso)" \
         last_status=success last_error=null last_exit_code=0 last_duration_s="$DUR"
else
  wstate last_finished_at="$(iso)" last_status=failed last_exit_code="$RC" \
         last_duration_s="$DUR" last_error="newsctl $SUBCMD exit=$RC (细节见 cron.log)"
fi
exit "$RC"
