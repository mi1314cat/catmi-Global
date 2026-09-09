#!/bin/sh
# watchdog-report.sh — Watchdog 服务端执行器（GitHub Actions 每天经 SSH 调一次）
# 检查: 项目 → Cron → 采集健康 → 锁; 修复: 仅 Cron 层面（幂等, 保留其他 Cron）
# 输出机器可读键值对; 退出码: 0=HEALTHY/RECOVERED, 1=DEGRADED, 2=FAIL
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJ=$(dirname "$SCRIPT_DIR")

echo "=== catmi-Global Serve00 Watchdog ==="
echo "WATCHDOG_TIME=$(TZ=UTC date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1) 项目文件
if [ ! -x "$PROJ/venv/bin/python" ] || [ ! -f "$PROJ/news-data/database/news.db" ]; then
  echo "PROJECT=BROKEN"
  echo "ACTION=NONE (不自动修复项目文件)"
  echo "RESULT=FAIL"
  exit 2
fi
echo "PROJECT=OK"

# 2) Cron（缺失/重复/损坏 → install-cron 幂等修复）
CR_OUT=$("$SCRIPT_DIR/check-cron.sh" 2>/dev/null); CR_RC=$?
CSTAT=$(printf '%s\n' "$CR_OUT" | sed -n 's/^CRON_STATUS=//p')
echo "CRON_STATUS=${CSTAT:-UNKNOWN}"
RESTORED=NO
case "${CSTAT:-UNKNOWN}" in
  OK) : ;;
  MISSING|DUPLICATE|INVALID)
    echo "ACTION=RESTORE_CRON"
    "$SCRIPT_DIR/install-cron.sh" >/dev/null 2>&1 || true
    "$SCRIPT_DIR/check-cron.sh" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
      RESTORED=YES; CSTAT=OK; echo "CRON_RESTORED=YES"
    else
      echo "CRON_RESTORED=FAILED_STILL_$CSTAT"
    fi
    ;;
  *) echo "ACTION=NONE (cron 状态未知, 不做危险操作)" ;;
esac

# 3) Collector 健康状态（来自 run-collector.sh 写的状态文件; 与 Cron 状态严格区分）
STATE="$PROJ/news-data/state/collector-state.json"
"$PROJ/venv/bin/python" - "$STATE" <<'PYEOF' >"$PROJ/news-data/state/.wd-collector.txt" 2>/dev/null
import datetime, json, os, subprocess, sys
try:
    st = json.load(open(sys.argv[1]))
except Exception:
    print("UNKNOWN"); raise SystemExit
now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
def ts(k):
    v = st.get(k)
    if not v:
        return None
    try:
        return datetime.datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None
# 正在运行?（[.] 防止匹配到自身/父 shell 的命令行）
try:
    out = subprocess.run(["pgrep", "-f", r"news[.]newsctl (run|cleanup|backup|doctor)"],
                         capture_output=True, text=True, timeout=10)
    running = bool(out.stdout.strip())
except Exception:
    running = False
if running:
    print("RUNNING"); raise SystemExit
succ, fin, started = ts("last_success_at"), ts("last_finished_at"), ts("last_started_at")
ls = st.get("last_status")
if ls == "running":
    # 有 started 无 finished 且进程不在 → 上轮被中断; 下一轮 cron 会自愈
    print("STALE"); raise SystemExit
if ls == "failed":
    if fin and (now - fin).total_seconds() <= 43200:
        print("FAILED_RECENT"); raise SystemExit
    print("STALE"); raise SystemExit
if succ and (now - succ).total_seconds() <= 4320:   # 72 分钟 = cron(10min) 的合理容忍上界
    print("OK"); raise SystemExit
if succ is None:
    print("UNKNOWN"); raise SystemExit
print("STALE")
PYEOF
ST=$(cat "$PROJ/news-data/state/.wd-collector.txt" 2>/dev/null || echo UNKNOWN)
rm -f "$PROJ/news-data/state/.wd-collector.txt"
echo "COLLECTOR_STATUS=$ST"

# 4) Lock 状态 — lockf 锁随进程死亡自动释放, 机制上不存在 stale lock;
#    /tmp/news-run.lock 文件本身在无进程时是惰性空文件, 永不删除（避免与运行中采集竞态）
if [ "$ST" = "RUNNING" ]; then
  LOCK_STATUS=RUNNING
else
  LOCK_STATUS=OK
fi
echo "LOCK_STATUS=$LOCK_STATUS"

# 5) 汇总（严格区分: Cron 修复 ≠ Collector 处理）
ACTION=NONE
case "$ST" in
  FAILED_RECENT) ACTION=NONE_RECORDED ;;      # 单次失败: 只记录, 不重建 Cron
  STALE)          ACTION=NONE_DEGRADED ;;     # 长期未成功: 标记, 不 kill/不删锁/不重启
esac
[ "$RESTORED" = "YES" ] && ACTION=RESTORE_CRON_DONE
echo "ACTION=$ACTION"

case "${CSTAT:-UNKNOWN}-$ST" in
  OK-OK|OK-RUNNING) RESULT=HEALTHY ;;
  OK-FAILED_RECENT|OK-STALE|OK-UNKNOWN) RESULT=DEGRADED ;;
  *) RESULT=FAIL ;;
esac
[ "$RESTORED" = "YES" ] && { [ "$RESULT" = "HEALTHY" ] || [ "$RESULT" = "DEGRADED" ]; } && RESULT=RECOVERED
echo "RESULT=$RESULT"

case "$RESULT" in
  HEALTHY|RECOVERED) exit 0 ;;
  DEGRADED) exit 1 ;;
  *) exit 2 ;;
esac
