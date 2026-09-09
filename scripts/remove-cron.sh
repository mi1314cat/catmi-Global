#!/bin/sh
# remove-cron.sh — 仅删除项目 Marker 区块, 用户其他 Cron 原样保留
set -u
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
B="# CATMI_GLOBAL_COLLECTOR_BEGIN"
E="# CATMI_GLOBAL_COLLECTOR_END"

CR=$(crontab -l 2>/dev/null || true)
if [ -z "$CR" ]; then echo "CRON_REMOVE=NOTHING_TO_DO"; exit 0; fi

KEEP=$(printf '%s\n' "$CR" | awk -v b="$B" -v e="$E" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}')

TMP=$(mktemp /tmp/crontab.XXXXXX) || exit 1
printf '%s\n' "$KEEP" >"$TMP"
if crontab "$TMP"; then
  rm -f "$TMP"
  echo "CRON_REMOVE=OK"
  exit 0
else
  rm -f "$TMP"
  echo "CRON_REMOVE=FAIL"
  exit 1
fi
