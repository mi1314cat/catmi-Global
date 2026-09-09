#!/bin/sh
# install-cron.sh — 幂等安装/修复项目 Cron 区块（只动自己的 Marker 区块, 保留其他所有 Cron）
# 第 1 次 → 添加; 第 2/3 次 → 不重复; 被删后 → 自动恢复; 用户其他 Cron → 原样保留
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJ=$(dirname "$SCRIPT_DIR")
B="# CATMI_GLOBAL_COLLECTOR_BEGIN"
E="# CATMI_GLOBAL_COLLECTOR_END"
LOGD="\$HOME/news-project/news-data/logs"

BLOCK="$B
*/10 * * * * $SCRIPT_DIR/run-collector.sh >> $LOGD/cron.log 2>&1
*/5 * * * * $SCRIPT_DIR/ai-worker.sh >> $LOGD/cron.log 2>&1
35 * * * * /bin/sh -c \"cd \$HOME/news-project && ./venv/bin/python -m news.newsctl cleanup\" >> $LOGD/cron.log 2>&1
10 4 * * * /bin/sh -c \"cd \$HOME/news-project && ./venv/bin/python -m news.newsctl backup\" >> $LOGD/cron.log 2>&1
20 4 * * * /bin/sh -c \"cd \$HOME/news-project && ./venv/bin/python -m news.newsctl doctor\" >> $LOGD/cron.log 2>&1
$E"

CR=$(crontab -l 2>/dev/null || true)

# 去掉所有旧项目区块（含重复区块）+ 迁移掉项目自己的旧式无 Marker 条目。
# 迁移仅精确匹配本项目的 news.newsctl / run-collector 模式——绝不会碰用户其他 Cron。
KEEP=""
if [ -n "$CR" ]; then
  KEEP=$(printf '%s\n' "$CR" | awk -v b="$B" -v e="$E" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}' | grep -Ev 'news[.]newsctl (run|cleanup|backup|doctor)|news-project/scripts/run-collector[.]sh' || true)
fi
# 去掉尾部多余空行, 保证区块前有一个空行分隔
KEEP=$(printf '%s\n' "$KEEP" | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba' -e '}')

TMP=$(mktemp /tmp/crontab.XXXXXX) || exit 1
{
  [ -n "$KEEP" ] && printf '%s\n' "$KEEP" && printf '\n'
  printf '%s\n' "$BLOCK"
} >"$TMP"

if crontab "$TMP"; then
  rm -f "$TMP"
  echo "CRON_INSTALL=OK"
else
  RC=$?
  rm -f "$TMP"
  echo "CRON_INSTALL=FAIL (crontab exited $RC)"
  exit 1
fi

"$SCRIPT_DIR/check-cron.sh"
