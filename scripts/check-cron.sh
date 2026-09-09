#!/bin/sh
# check-cron.sh — 项目 Cron 区块检查（机器可读输出, 不打印任何 Secret）
# 输出: CRON_STATUS=OK|MISSING|DUPLICATE|INVALID
# 退出: 0=OK, 非0=有问题
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJ=$(dirname "$SCRIPT_DIR")
RUNNER="$SCRIPT_DIR/run-collector.sh"
B="# CATMI_GLOBAL_COLLECTOR_BEGIN"
E="# CATMI_GLOBAL_COLLECTOR_END"

CR=$(crontab -l 2>/dev/null || true)
if [ -z "$CR" ]; then
  echo "CRONTAB_EXISTS=NO"
  echo "CRON_STATUS=MISSING"
  exit 1
fi
echo "CRONTAB_EXISTS=YES"

BC=$(printf '%s\n' "$CR" | grep -Fxc "$B" || true)
EC=$(printf '%s\n' "$CR" | grep -Fxc "$E" || true)
echo "MARKER_BEGIN_COUNT=$BC"
echo "MARKER_END_COUNT=$EC"

if [ "$BC" -eq 0 ] || [ "$EC" -eq 0 ]; then
  echo "CRON_STATUS=MISSING"; exit 1
fi
if [ "$BC" -ne "$EC" ]; then
  echo "CRON_STATUS=INVALID"; echo "CRON_REASON=unbalanced_markers"; exit 1
fi
if [ "$BC" -gt 1 ]; then
  echo "CRON_STATUS=DUPLICATE"; exit 1
fi

BLOCK=$(printf '%s\n' "$CR" | awk -v b="$B" -v e="$E" '$0==b{f=1;next} $0==e{f=0;next} f')
RL=$(printf '%s\n' "$BLOCK" | grep -Fc "run-collector.sh" || true)
if [ "$RL" -lt 1 ]; then
  echo "CRON_STATUS=INVALID"; echo "CRON_REASON=no_runner_line"; exit 1
fi
if [ ! -f "$RUNNER" ] || [ ! -x "$RUNNER" ]; then
  echo "CRON_STATUS=INVALID"; echo "CRON_REASON=runner_missing_or_not_executable"; exit 1
fi
# 块内引用的 $HOME/news-project/... 路径必须真实存在
BAD=$(printf '%s\n' "$BLOCK" | grep -oE '\$HOME/news-project/[A-Za-z0-9/._-]+' | sort -u | \
      while IFS= read -r p; do
        t="$HOME/${p#\$HOME/}"
        case "$t" in *'*'*) continue ;; esac
        [ -e "$t" ] || echo "$p"
      done)
if [ -n "$BAD" ]; then
  echo "CRON_STATUS=INVALID"
  echo "CRON_REASON=missing_path:$BAD" | tr '\n' ' '; echo
  exit 1
fi

LINES=$(printf '%s\n' "$BLOCK" | grep -c . || true)
echo "CRON_LINES=$LINES"
echo "CRON_STATUS=OK"
exit 0
