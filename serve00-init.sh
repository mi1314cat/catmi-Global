#!/usr/bin/env bash
#
# serve00-init.sh — Serv00 新闻系统基础环境初始化脚本
#
# 设计原则（见 INIT_DESIGN.md）:
#   * 幂等：运行一次与运行十次结果一致，不产生重复配置
#   * 保守：只补缺失内容，绝不删除未知文件，绝不覆盖已有配置
#   * 保护：绝不修改 devil www / SSL / DNS / 平台配置；默认绝不修改 crontab
#   * 秘密：脚本与产物中禁止出现任何密码 / Token / API Key / 私钥
#   * 回滚：install 创建的每一项都登记在 .init-manifest，uninstall 只删除清单内条目
#
# 用法:
#   ./serve00-init.sh check | install | repair | status | doctor | uninstall [--dry-run] [--with-cron] [--yes] [--remove-cron] [--purge-backups]
#
VERSION="1.0.1"
DOMAIN="myp.micsdic.dpdns.org"
PROJECT="$HOME/news-project"
DATA="$PROJECT/news-data"
VENV="$PROJECT/venv"
MANIFEST="$PROJECT/.init-manifest"
BACKUPS="$HOME/news-backups/init"
CRON_BEGIN="# BEGIN serve00-news (managed by serve00-init.sh)"
CRON_END="# END serve00-news"

MODE=""
DRY_RUN=0
WITH_CRON=0
ASSUME_YES=0
REMOVE_CRON=0
PURGE_BACKUPS=0

for a in "$@"; do
  case "$a" in
    check|install|repair|status|doctor|uninstall|wizard) MODE="$a" ;;
    --dry-run) DRY_RUN=1 ;;
    --with-cron) WITH_CRON=1 ;;
    --yes) ASSUME_YES=1 ;;
    --remove-cron) REMOVE_CRON=1 ;;
    --purge-backups) PURGE_BACKUPS=1 ;;
    -h|--help) MODE="help" ;;
  wizard) MODE="wizard" ;;
    *) ;;
  esac
done

if [ -t 1 ]; then
  C_G="\033[32m"; C_Y="\033[33m"; C_R="\033[31m"; C_B="\033[36m"; C_0="\033[0m"
else
  C_G=""; C_Y=""; C_R=""; C_B=""; C_0=""
fi
info()  { printf "${C_B}[*]${C_0} %s\n" "$*"; }
ok()    { printf "${C_G}[OK]${C_0} %s\n" "$*"; }
warn()  { printf "${C_Y}[WARN]${C_0} %s\n" "$*"; }
err()   { printf "${C_R}[!!]${C_0} %s\n" "$*"; }
step()  { printf "\n${C_B}=== %s ===${C_0}\n" "$*"; }

# dry-run 感知的执行器：DRY_RUN=1 时只打印将要执行的动作
act() {
  if [ "$DRY_RUN" = "1" ]; then
    printf "${C_Y}[dry-run]${C_0} %s\n" "$*"
  else
    eval "$@"
  fi
}

ensure_dir() {
  # 支持多个参数：逐一确保存在并登记 manifest（v1.0.1 修复：此前只处理 $1）
  for _d in "$@"; do
    if [ -d "$_d" ]; then
      ok "目录已存在: $_d"
    else
      info "创建目录: $_d"
      act "mkdir -p '$_d'"
    fi
    if [ "$DRY_RUN" != "1" ] && [ -d "$_d" ]; then
      add_manifest "dir|$_d"
    fi
  done
}

add_manifest() {
  _entry="$1"
  if [ ! -f "$MANIFEST" ]; then : > "$MANIFEST"; fi
  if ! grep -qxF "$_entry" "$MANIFEST"; then
    echo "$_entry" >> "$MANIFEST"
  fi
}

http_code() {
  curl -s -o /dev/null -m 12 -w '%{http_code}' "$1" 2>/dev/null || echo 000
}

have() { command -v "$1" >/dev/null 2>&1; }

days_until() {
  # 参数: YYYY.MM.DD 或 YYYY-MM-DD；优先 BSD date，回退 GNU date
  _d="$(echo "$1" | tr '.' '-')"
  if date -j -f "%Y-%m-%d" "$_d" +%s >/dev/null 2>&1; then
    echo $(( ( $(date -j -f "%Y-%m-%d" "$_d" +%s) - $(date +%s) ) / 86400 ))
  elif date -d "$_d" +%s >/dev/null 2>&1; then
    echo $(( ( $(date -d "$_d" +%s) - $(date +%s) ) / 86400 ))
  else
    echo "?"
  fi
}

# ---------------- 检查函数（全部只读） ----------------

check_system() {
  step "系统"
  info "OS: $(uname -s) $(uname -r) $(uname -m)"
  info "主机: $(hostname 2>/dev/null)  用户: $(whoami)"
  info "CPU 核数: $(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo '?')"
  _mem=$(sysctl -n hw.physmem 2>/dev/null || echo 0)
  [ "$_mem" -gt 0 ] 2>/dev/null && info "物理内存(整机共享): $(( _mem / 1024 / 1024 / 1024 )) GB"
  info "磁盘(家目录所在卷):"
  df -h "$HOME" 2>/dev/null | tail -1 | sed 's/^/    /'
  info "inode:"
  df -i "$HOME" 2>/dev/null | tail -1 | sed 's/^/    /'
  if have devil; then
    _lim=$(devil info limits 2>/dev/null | sed -e 's/\x1b\[[0-9;]*m//g')
    _disk=$(echo "$_lim" | grep 'Disk quota' | grep -oE '[0-9.]+% \([0-9.]+[KMG]/[0-9.]+[KMG]\)' | head -1)
    _ram=$(echo "$_lim" | grep 'RAM memory' | grep -oE '[0-9.]+% \([0-9.]+[KMG]/[0-9.]+[KMG]\)' | head -1)
    _proc=$(echo "$_lim" | grep 'Processes' | grep -oE '[0-9.]+% \([0-9]+/[0-9]+\)' | head -1)
    info "配额: disk=$_disk ram=$_ram proc=$_proc"
  else
    warn "devil CLI 不可用（不在 PATH），平台限额信息跳过"
  fi
}

check_runtimes() {
  step "运行时"
  _py=$(python3 --version 2>/dev/null) && ok "$_py" || err "python3 不可用"
  _pip=$(python3 -m pip --version 2>/dev/null | awk '{print $1,$2}') \
    && ok "pip: $_pip (python3 -m pip)" || warn "pip 不可用（python3 -m pip）"
  have php    && ok "php: $(php -v 2>/dev/null | head -1 | awk '{print $1,$2}')"  || warn "php 不可用"
  have git    && ok "git: $(git --version 2>/dev/null | awk '{print $3}')"        || warn "git 不可用"
  have node   && ok "node: $(node --version 2>/dev/null)"                          || warn "node 不可用"
  have sqlite3 && ok "sqlite3: $(sqlite3 --version 2>/dev/null | awk '{print $1}')" || warn "sqlite3 不可用"
  have mysql  && ok "mysql 客户端: $(mysql --version 2>/dev/null | awk '{print $5,$6}')" || warn "mysql 客户端不可用"
  have psql   && ok "psql: $(psql --version 2>/dev/null | awk '{print $3}')"       || warn "psql 不可用"
  if [ -x "$VENV/bin/python" ]; then
    ok "项目 venv: $($VENV/bin/python --version 2>&1)"
  else
    warn "项目 venv 不存在（install 模式会创建）"
  fi
}

check_web() {
  step "Web / 域名（只读检查，绝不修改）"
  if ! have devil; then err "devil 不可用，无法检查网站配置"; return 1; fi
  _www=$(devil www list 2>/dev/null | sed -e 's/\x1b\[[0-9;]*m//g')
  if echo "$_www" | grep -q "$DOMAIN"; then
    _line=$(echo "$_www" | grep "$DOMAIN" | head -1 | sed 's/  */ /g')
    ok "受保护域名已绑定: $_line"
  else
    warn "域名 $DOMAIN 不在 devil www list 中（如需恢复请到面板操作，脚本不会自动创建）"
  fi
  if [ -d "$HOME/domains" ]; then
    info "域名目录: $(ls "$HOME/domains" 2>/dev/null | tr '\n' ' ')"
  fi
  _ht=$(find "$HOME/domains" -maxdepth 3 -name '.htaccess' 2>/dev/null | head -3)
  if [ -n "$_ht" ]; then info "发现 .htaccess: $_ht"; else info "未发现 .htaccess（nodejs 站点正常）"; fi
}

check_ssl() {
  step "SSL（只读检查，绝不输出私钥）"
  if ! have devil; then err "devil 不可用，SSL 检查跳过"; return 1; fi
  _ssl=$(devil ssl www list 2>/dev/null | sed -e 's/\x1b\[[0-9;]*m//g')
  _line=$(echo "$_ssl" | grep "$DOMAIN" | head -1)
  if [ -n "$_line" ]; then
    _cn=$(echo "$_line" | awk '{print $1}')
    _exp=$(echo "$_line" | grep -oE '[0-9]{4}\.[0-9]{2}\.[0-9]{2}' | tail -1)
    ok "已配置证书: CN=$_cn 过期=$_exp"
    _days=$(days_until "$_exp")
    if [ "$_days" = "?" ]; then warn "证书有效期解析失败（人工核对）"
    elif [ "$_days" -lt 0 ]; then err "证书已过期($_days 天)！"
    elif [ "$_days" -lt 30 ]; then warn "证书 30 天内到期: 剩余 ${_days} 天"
    else ok "证书剩余 ${_days} 天"
    fi
  else
    warn "未在 devil ssl www list 中找到 $DOMAIN 的证书"
  fi
  _code=$(http_code "https://$DOMAIN/")
  case "$_code" in
    200|301|302) ok "HTTPS 可访问: HTTP $_code" ;;
    000) warn "HTTPS 无法连接（可能网络波动）" ;;
    *) warn "HTTPS 返回 $_code" ;;
  esac
}

check_network() {
  step "网络（少量探测请求）"
  info "DNS: $(host "$DOMAIN" 2>/dev/null | head -1 || echo '解析失败')"
  _g=$(http_code "https://github.com");   [ "$_g" = "200" ] && ok "GitHub: $_g" || warn "GitHub: $_g"
  _p=$(http_code "https://pypi.org/simple/"); [ "$_p" = "200" ] && ok "PyPI: $_p" || warn "PyPI: $_p"
  _e=$(http_code "https://example.com");  [ "$_e" = "200" ] && ok "通用 HTTPS: $_e" || warn "通用 HTTPS: $_e"
}

check_cron() {
  step "Cron（只读，默认绝不修改）"
  if crontab -l >/dev/null 2>&1; then
    _n=$(crontab -l 2>/dev/null | grep -cvE '^[[:space:]]*#|^[[:space:]]*$')
    info "当前 crontab 非注释行数: $_n"
    if crontab -l 2>/dev/null | grep -qF "$CRON_BEGIN"; then
      info "检测到本脚本的标记 cron 块（serve00-news）"
    else
      info "未发现 serve00-news cron 标记块"
    fi
    ok "确认：本脚本除非显式 --with-cron / --remove-cron，否则不会写入 crontab"
  else
    info "当前用户无 crontab"
  fi
}

check_project() {
  step "项目目录"
  if [ -d "$PROJECT" ]; then
    ok "项目目录存在: $PROJECT"
    [ -f "$MANIFEST" ] && info "manifest 条目数: $(wc -l < "$MANIFEST" | tr -d ' ')"
    info "顶层内容: $(ls -A "$PROJECT" 2>/dev/null | tr '\n' ' ')"
  else
    warn "项目目录不存在: $PROJECT（install 模式会创建）"
  fi
  if [ -d "$BACKUPS" ]; then ok "备份目录存在: $BACKUPS"; else warn "备份目录不存在: $BACKUPS"; fi
}

run_all_checks() {
  check_system
  check_runtimes
  check_web
  check_ssl
  check_network
  check_cron
  check_project
}

# ---------------- 模式实现 ----------------

cmd_help() {
  cat <<EOF
serve00-init.sh v$VERSION — Serv00 新闻系统基础环境初始化

用法: ./serve00-init.sh <模式> [选项]
模式:
  check      只检查环境，不修改任何东西
  install    创建缺失的基础结构（项目目录/venv/模板），幂等
  repair     修复可安全修复的基础项（目录/venv），绝不触碰域名/SSL/cron
  status     简要显示当前环境状态
  doctor     全面诊断（含阈值判断与结论）
  uninstall  仅删除 .init-manifest 中登记的条目（绝不触碰域名/SSL/平台文件）
选项:
  --dry-run      演练模式：只显示将执行的动作
  --with-cron    install 时写入注释版 cron 占位块（默认不写；先备份 crontab）
  --remove-cron  uninstall 时移除 serve00-news 标记 cron 块（先备份）
  --yes          uninstall 不交互确认
  --purge-backups uninstall 时连 $BACKUPS 一起删除（默认保留）

保护对象（任何模式都不会修改）:
  * devil www / ssl / DNS 配置
  * $DOMAIN 及其证书
  * 用户已有 crontab（除非显式 --with-cron / --remove-cron）
  * ~/backups（平台 ZFS 快照）
EOF
}

cmd_install() {
  step "install（幂等，只补缺失）"
  ensure_dir "$PROJECT"
  ensure_dir "$DATA" "$DATA/articles" "$DATA/images" "$DATA/database" "$DATA/cache" "$DATA/logs" \
             "$PROJECT/sites" "$BACKUPS"
  if [ ! -x "$VENV/bin/python" ]; then
    info "创建 Python venv..."
    act "python3 -m venv '$VENV'"
    if [ "$DRY_RUN" != "1" ] && [ -x "$VENV/bin/python" ]; then
      add_manifest "venv|$VENV"
      info "venv 内升级 pip（失败不阻塞）"
      "$VENV/bin/python" -m pip install --quiet --upgrade pip 2>/dev/null \
        && ok "pip 已就绪" || warn "pip 升级失败（可稍后手动执行）"
    fi
  else
    ok "venv 已存在: $VENV"
  fi
  if [ ! -f "$PROJECT/env.example" ]; then
    info "写入 env.example（空值模板，无任何秘密）"
    act "cat > '$PROJECT/env.example'"
    if [ "$DRY_RUN" != "1" ]; then
      cat > "$PROJECT/env.example" <<'ENVEOF'
# serve00-news 环境变量模板 —— 运行时填写，禁止提交真实值到任何公开文件
# AI（OpenAI-compatible；可换 DeepSeek/Qwen/Gemini 等兼容端点）
OPENAI_BASE_URL=
OPENAI_API_KEY=
# 采集限制（资源保护）
FETCH_CONCURRENCY=2
REQUEST_TIMEOUT=20
RETRY_MAX=3
IMAGE_MAX_MB=8
ARTICLE_MAX_CHARS=200000
# 存储保护
DISK_THRESHOLD_PCT=80
INODE_THRESHOLD_PCT=80
ENVEOF
      add_manifest "file|$PROJECT/env.example"
    fi
  else
    ok "env.example 已存在（不覆盖）"
  fi
  if [ ! -f "$PROJECT/PROJECT_README.txt" ]; then
    info "写入 PROJECT_README.txt（项目说明指针）"
    if [ "$DRY_RUN" != "1" ]; then
      {
        echo "Serve00 新闻采集系统"
        echo "  初始化/检查: ./serve00-init.sh check|install|repair|status|doctor"
        echo "  文档: README.md / INIT_DESIGN.md / INIT_CHANGELOG.md（与本脚本同目录）"
        echo "  数据: news-data/{articles,images,database,cache,logs}"
        echo "  站点适配器: sites/"
        echo "  虚拟环境: ./venv/bin/python"
        echo "  注意: env 填写到本地私有文件（如 env.local，加入忽略），不进 Git"
      } > "$PROJECT/PROJECT_README.txt"
      add_manifest "file|$PROJECT/PROJECT_README.txt"
    fi
  else
    ok "PROJECT_README.txt 已存在（不覆盖）"
  fi
  if [ "$WITH_CRON" = "1" ]; then
    install_cron_block
  else
    info "未指定 --with-cron：不修改 crontab。建议的 cron 占位块如下（当前全部注释，激活在后续阶段）:"
    print_cron_block | sed 's/^/    /'
  fi
  # 安装完成后做只读验证
  _code=$(http_code "https://$DOMAIN/")
  [ "$_code" = "200" ] && ok "验证: $DOMAIN HTTPS 仍为 200" || warn "验证: $DOMAIN HTTPS 返回 $_code"
  ok "install 完成（幂等，可重复执行）"
}

print_cron_block() {
  cat <<CRONEOF
$CRON_BEGIN
# 占位（后续阶段激活；激活前先 ./serve00-init.sh check 确认 crontab 无冲突）
# */10 * * * * cd $PROJECT && ./venv/bin/python newscli.py scan --batch 20 >> news-data/logs/cron.log 2>&1
$CRON_END
CRONEOF
}

install_cron_block() {
  if crontab -l 2>/dev/null | grep -qF "$CRON_BEGIN"; then
    ok "cron 标记块已存在（幂等，跳过）"
    return
  fi
  info "备份现有 crontab 到 $BACKUPS"
  act "crontab -l > '$BACKUPS/crontab-backup-\$(date +%Y%m%d-%H%M%S).txt' 2>/dev/null || true"
  info "追加 serve00-news 标记 cron 块（注释占位，不激活任务）"
  if [ "$DRY_RUN" != "1" ]; then
    ( crontab -l 2>/dev/null; echo ""; print_cron_block ) | crontab - \
      && ok "cron 块已写入（占位未激活）" || err "crontab 写入失败"
  fi
}

remove_cron_block() {
  if ! crontab -l 2>/dev/null | grep -qF "$CRON_BEGIN"; then
    info "无 serve00-news cron 块，跳过"
    return
  fi
  info "备份 crontab 后移除 serve00-news 标记块"
  act "crontab -l > '$BACKUPS/crontab-backup-\$(date +%Y%m%d-%H%M%S).txt'"
  if [ "$DRY_RUN" != "1" ]; then
    crontab -l > "$BACKUPS/crontab-before-remove.txt"
    awk -v b="$CRON_BEGIN" -v e="$CRON_END" '
      index($0, b) { inblk=1; next }
      inblk && index($0, e) { inblk=0; next }
      inblk { next }
      { print }
    ' "$BACKUPS/crontab-before-remove.txt" > "$BACKUPS/crontab-after-remove.txt"
    crontab "$BACKUPS/crontab-after-remove.txt" \
      && ok "cron 块已移除（备份: $BACKUPS/crontab-before-remove.txt）" || err "crontab 恢复失败"
  fi
}

cmd_repair() {
  step "repair（只修复可安全修复项）"
  ensure_dir "$PROJECT" "$DATA" "$DATA/articles" "$DATA/images" "$DATA/database" "$DATA/cache" "$DATA/logs" "$PROJECT/sites" "$BACKUPS"
  if [ ! -x "$VENV/bin/python" ]; then
    if [ -d "$VENV" ]; then
      _ts=$(date +%Y%m%d-%H%M%S)
      warn "venv 存在但损坏，移入 $BACKUPS/venv-broken-$_ts 后重建"
      act "mv '$VENV' '$BACKUPS/venv-broken-$_ts'"
    fi
    info "重建 venv"
    act "python3 -m venv '$VENV'"
    [ "$DRY_RUN" != "1" ] && add_manifest "venv|$VENV"
  else
    ok "venv 完好"
  fi
  # 只读复核受保护对象
  check_web
  check_ssl
  ok "repair 完成（域名/SSL/cron 未被触碰）"
}

cmd_doctor() {
  step "doctor 全面诊断"
  run_all_checks
  step "阈值与结论"
  _usedp=$(df -h "$HOME" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
  if [ -n "$_usedp" ] && [ "$_usedp" -ge 80 ] 2>/dev/null; then
    warn "磁盘使用率 ${_usedp}% >= 80%（采集系统需启用清理策略）"
  else
    ok "磁盘使用率 ${_usedp:-?}%"
  fi
  if have devil; then
    _lim=$(devil info limits 2>/dev/null | sed -e 's/\x1b\[[0-9;]*m//g')
    _ram=$(echo "$_lim" | grep 'RAM memory' | grep -oE '[0-9.]+%' | head -1 | tr -d '%')
    _pc=$(echo "$_lim" | grep 'Processes' | grep -oE '\([0-9]+/[0-9]+\)' | head -1 | tr -d '()')
    _ramn=${_ram:-0}; _pcn=${_pc:-0/20}
    [ "$_ramn" -ge 80 ] 2>/dev/null && warn "内存占用 ${_ramn}%（限制浏览器类组件）" || ok "内存占用 ${_ramn}%"
    info "进程使用 ${_pcn}（上限 20：采集器并发必须受控）"
  fi
  _code=$(http_code "https://$DOMAIN/")
  [ "$_code" = "200" ] && ok "结论: 受保护域名 HTTPS 正常" || err "结论: $DOMAIN HTTPS 异常($_code)，人工检查！"
  if have python3 && have git && have sqlite3; then
    ok "结论: 基础运行时齐备（Python/Git/SQLite），适合部署采集系统"
  else
    err "结论: 基础运行时缺失，见上方 WARN 项"
  fi
  info "说明: FreeBSD 无官方 Playwright/Chromium 支持，JS 重度站点策略见 SCRAPER_DECISIONS.md"
}

cmd_uninstall() {
  step "uninstall（只删 .init-manifest 内条目）"
  if [ ! -f "$MANIFEST" ]; then
    warn "未找到 manifest: $MANIFEST —— 本脚本未在此机器安装过任何东西，退出"
    return
  fi
  if [ "$ASSUME_YES" != "1" ] && [ "$DRY_RUN" != "1" ]; then
    printf "将删除 manifest 登记的 %s 个条目（域名/SSL/平台文件绝不触碰）。继续? [y/N] " "$(wc -l < "$MANIFEST" | tr -d ' ')"
    read -r _ans
    case "$_ans" in y|Y|yes|YES) ;; *) warn "已取消"; return ;; esac
  fi
  if [ "$REMOVE_CRON" = "1" ]; then remove_cron_block; fi
  # 倒序处理（FreeBSD 无 GNU tac，用 awk 反转）
  awk '{a[NR]=$0} END {for(i=NR;i>=1;i--) print a[i]}' "$MANIFEST" | while IFS='|' read -r _t _p; do
    [ -z "${_t:-}" ] && continue
    case "$_p" in
      "$HOME/domains"*|"$HOME/backups"*) err "拒绝删除受保护路径: $_p"; continue ;;
    esac
    case "$_t" in
      file) [ -f "$_p" ] && { info "删除文件: $_p"; act "rm -f '$_p'"; } ;;
      dir)  [ -d "$_p" ] && { info "删除空目录: $_p"; act "rmdir '$_p' 2>/dev/null || warn '非空，跳过: $_p'"; } ;;
      venv) [ -d "$_p" ] && { info "删除 venv: $_p"; act "rm -rf '$_p'"; } ;;
    esac
  done
  if [ "$PURGE_BACKUPS" = "1" ]; then
    info "删除备份目录: $BACKUPS"
    act "rm -rf '$BACKUPS'"
  else
    ok "备份保留在 $BACKUPS（--purge-backups 可删除）"
  fi
  info "注: $HOME/domains 与平台配置（devil/DNS/SSL/邮箱）不受 uninstall 影响"
  ok "uninstall 完成"
}

# ==================== 向导模式 (一键安装引导) ====================
# 用法: bash serve00-init.sh wizard
#   交互式完成: 域名 → (可选)证书粘贴 → (可选)端口自动申请 → env.local+Token → 汇总
ENV_LOCAL="$PROJECT/env.local"

wizard_welcome() {
  echo "=============================================="
  echo "  Global Intelligence 一键安装向导 (Serv00)"
  echo "=============================================="
  echo "原则与 install 相同: 幂等/保守/清单回滚/不出秘密。"
}

wizard_parse_port_list() {   # 仿 serv00-play 借鉴: 解析 devil port list → 数组
  PORT_ARRAY=""
    # 输出行格式: <端口> <typ(tcp/udp)> <描述>; 只取描述含标记的 tcp 项
  PORT_PORT=$(devil port list 2>/dev/null | awk -v d="$WIZ_PORT_DESC" '$2 ~ /tcp/ && $0 ~ d && $1 ~ /^[0-9]+$/ {print $1}' | tail -1)
}

wizard_get_port() {          # 借鉴 frankiejun/serv00-play getPort()
  WIZ_PORT_DESC="${WIZ_PORT_DESC:-gi-news}"
  wizard_parse_port_list
  if [[ -n "$PORT_PORT" ]]; then
    WIZ_PORT="$PORT_PORT"; return 0
  fi
  local rt; rt=$(devil port add tcp random "$WIZ_PORT_DESC" 2>/dev/null)
  if [[ "$rt" == *successfully* || "$rt" == *Ok* ]]; then
    wizard_parse_port_list
    if [[ -n "$PORT_PORT" ]]; then WIZ_PORT="$PORT_PORT"; return 0; fi
  fi
  return 1
}

wizard() {
  wizard_welcome
  # --- 1) 域名 ---
  local user; user=$(whoami)
  echo ""
  echo "① 绑定域名"
  echo "   默认(无明显出境入口时): ${user}.serv00.net"
  read -rp "   输入对外域名 [${user}.serv00.net]: " WIZ_DOMAIN
  WIZ_DOMAIN=${WIZ_DOMAIN:-${user}.serv00.net}
  # --- 2) 路线: Cloudflare 套盾 vs 直连自持证书 ---
  echo ""
  echo "② 证书"
  echo "   A) 域名前面有 Cloudflare (推荐, Serv00 上免证书)"
  echo "   B) 直连裸域名, 需要粘贴你自己的证书"
  read -rp "   选 A/B [A]: " WIZ_SSLROUTE; WIZ_SSLROUTE=${WIZ_SSLROUTE:-A}
  if [[ "$WIZ_SSLROUTE" == "B" ]]; then
    CERT_DIR="$HOME/certs"; mkdir -p "$CERT_DIR"; chmod 700 "$CERT_DIR"
    read -rp "   证书保存的域名文件名 [$WIZ_DOMAIN]: " CF; CF=${CF:-$WIZ_DOMAIN}
    CERT_PATH="$CERT_DIR/$CF.crt"; KEY_PATH="$CERT_DIR/$CF.key"
    echo "📄 请粘贴证书( -----BEGIN CERTIFICATE----- 开头, Ctrl+D 结束):"
    CERT_CONTENT=$(</dev/stdin)
    [[ -z "$CERT_CONTENT" ]] && { echo "❌ 证书内容不能为空"; return 1; }
    echo "$CERT_CONTENT" > "$CERT_PATH"; chmod 600 "$CERT_PATH"
    echo "🔑 请粘贴私钥( -----BEGIN PRIVATE KEY----- 或 RSA 开头, Ctrl+D 结束):"
    KEY_CONTENT=$(</dev/stdin)
    [[ -z "$KEY_CONTENT" ]] && { echo "❌ 私钥不能为空"; return 1; }
    echo "$KEY_CONTENT" > "$KEY_PATH"; chmod 600 "$KEY_PATH"
    echo "✅ 已保存(600): $CERT_PATH  $KEY_PATH"
    echo "ℹ️  Serv00 域名 SSL 在面板 Domain details 里上传, 或用 devil ssl add; 脚本不替你操作 SSL 平台配置。"
    unset CERT_CONTENT KEY_CONTENT   # 不驻留内存
  else
    echo "ℹ️  Cloudflare 路线: 边缘证书由 CF 处理, Serv00 无需证书。域名解析请指到 CF。"
  fi
  # --- 3) 端口(可选) ---
  echo ""
  echo "③ 端口"
  echo "   Web/MCP 走 Passenger 443, 不需要额外端口。此处可选申请一个裸 TCP 端口备用。"
  read -rp "   尝试自动申请(tcp random)? [y/N]: " WANT_PORT; WANT_PORT=${WANT_PORT:-N}
  WIZ_PORT=""
  if [[ "${WANT_PORT,,}" == "y" ]]; then
    if wizard_get_port; then
      echo "   ✅devil 自动分配端口: $WIZ_PORT (描述: $WIZ_PORT_DESC)"
    else
      echo "   ⚠️ 自动分配失败 — 请到面板 Ports 页手工申请, 然后重启向导或手工记录。"
    fi
  fi
  # --- 4) env.local + MCP_TOKEN ---
  echo ""
  echo "④ env.local / MCP_TOKEN"
  if [[ -f "$ENV_LOCAL" ]]; then
    echo "   已有 $ENV_LOCAL 保持不动(不覆盖秘密)。"
  else
    read -rp "   生成随机 MCP_TOKEN 并写入? [Y/n]: " GEN_T; GEN_T=${GEN_T:-y}
    if [[ "${GEN_T,,}" != "n" ]]; then
      MODE="status"   # 复用环境检查
      MCP_TOKEN_GEN=$(head -c 64 /dev/urandom 2>/dev/null | od -An -tx1 | tr -d ' \n') || true
      if [ -z "$MCP_TOKEN_GEN" ]; then MCP_TOKEN_GEN=$(/usr/bin/openssl rand -hex 32 2>/dev/null || /bin/dd if=/dev/urandom bs=32 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n'); fi
      mkdir -p "$(dirname "$ENV_LOCAL")"; touch "$ENV_LOCAL"; chmod 600 "$ENV_LOCAL"
      printf 'MCP_TOKEN=%s\n# AI/搜索 provider key 均为可选 — 见 env.local.example\n' "$MCP_TOKEN_GEN" > "$ENV_LOCAL"
      chmod 600 "$ENV_LOCAL"
      echo "   ✅ 已写入 $ENV_LOCAL (600)"
    fi
  fi
  # --- 5) 基础安装 ---
  echo ""
  echo "⑤ 运行 install (env/venv/数据目录)?"
  read -rp "   立即 install? [y/N]: " GOI; GOI=${GOI:-n}
  [[ "${GOI,,}" == "y" ]] && { MODE="install"; do_install || true; }
  # --- 6) 汇总 ---
  echo ""
  echo "=============================================="
  echo "✅ 向导完成。接下来:"
  echo "   1. (Serv00 面板) devil www add $WIZ_DOMAIN public_nodejs 或面板 Pages 指向 web/"
  echo "   2. 建号: cd web && node -e \"console.log(require('./lib/auth.js').createUser('admin','你的强密码','admin'))\""
  echo "      或启动后在 ~/news-project/admin-credentials.txt 找引导管理员"
  echo "   3. MCP 接入: {\"mcpServers\":{\"global-intelligence\":{\"url\":\"https://$WIZ_DOMAIN/mcp\",\"headers\":{\"Authorization\":\"Bearer <Token>\"}}}}"
  [[ -n "$WIZ_PORT" ]] && echo "   备用TCP端口: $WIZ_PORT"
  echo "=============================================="
}

# ---------------- 入口 ----------------

case "${MODE:-}" in
  check)     run_all_checks;  ok "check 完成（未做任何修改）" ;;
  status)    check_system; check_web; check_ssl; check_project; check_cron ;;
  install)   cmd_install ;;
  repair)    cmd_repair ;;
  doctor)    cmd_doctor ;;
  uninstall) cmd_uninstall ;;
  wizard)    wizard ;;
  help)      cmd_help ;;
  *)         echo "未知模式: ${MODE}" >&2; cmd_help; exit 2 ;;
esac
