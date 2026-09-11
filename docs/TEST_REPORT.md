# TEST_REPORT — 独立 QA 报告追踪（Developer 维护）

> QA 来源: 独立测试 Agent (工作区审计 + MCP 黑盒)。Developer 逐项验证后修复; 修复后由 QA 复验。
> 修复批次: 2026-09-09 Stabilization Round 1 (commit 见 git log)

| ID | Sev | Component | 问题 | 根因 | 修复 | 状态/回归 |
|---|---|---|---|---|---|---|
| QA-1 | High | websearch.js bingNewsRss | &amp; 未解码→解包静默失败→domain_cap 误杀 9 条/deep_search 读假页 | URL 参数名变 amp;url | item-slice 重写: 先解码实体再解包 url=/u=, publisher_domain/canonical_url 回填, description→snippet | ✅ FIXED: bingnews 2条真实域名(pna.gov.ph/irishtimes.com)+snippet 非空 |
| QA-2 | Med | websearch.js fetchText | 重定向环无深度上限 | 递归无 depth | depth>5 拒绝 | ✅ FIXED |
| QA-3 | Med | websearch.js gnewsRss | snippet 全空 | 未读 description | item 内提取 description→snippet | ✅ FIXED |
| QA-4 | High | newsdb.js trending | hours 参数完全失效(当主键匹配) | window_hours=? | window_hours=24 固定 + st.last_updated>=isoAgo(hours) | ✅ FIXED: hours=48 返回 3 条 |
| QA-5 | High | newsdb.js searchEvents | source_count=文章数(52)覆盖真实独立来源(18) | COUNT(*) | COUNT(DISTINCT source_id) | ✅ FIXED: 11(=DISTINCT) |
| QA-6 | High | reader.js | 并发≥3 永久 pending | queue 只 push 不排空 | finish() 补 queue.shift() drain | ✅ FIXED (未在 QA 清单验证细节, 代码级修复) |
| QA-7 | High | reader.py | consent/redirect 页判 ok | 只看提取成功 | 内容门禁 <400字或 INTERSTITIAL 特征→needs_js | ✅ FIXED: google.com→needs_js (曾因门禁插错位置致 UnboundLocalError, 已修) |
| QA-8 | High | reader.py infer_published | body_regex 从任意正文臆造日期 | 正则兜底 | 移除 body_regex 层 | ✅ FIXED |
| QA-9 | High | newsdb.js getEventDetail/getStory | SELECT * 带 fingerprint→get_event 29KB 溢出 | SELECT * | 字段白名单 | ✅ FIXED: 8.4KB 无 fingerprint |
| QA-10 | Med | newsdb.js searchEvents cnt | COUNT(*) 错误来源计数 | 同 QA-5 | 同上 | ✅ FIXED |
| QA-11 | Med | newsdb.js/app.js | search_intelligence 三重冗余 | stories 带 articles | handler 解构剥离 articles | ✅ FIXED |
| QA-12 | Med | app.js search_events | 50 事件各查 evidence | 无上限 | evidence 只附 top-5 | ✅ FIXED |
| QA-13 | Med | websearch.js region | region 键名不一致→ddg 恒默认 | opts.region_ddg | 兼容 opts.region | ✅ FIXED |
| QA-14 | High | rerank | time_range 静默失效 | provider 不支持 | 硬过滤 out_of_window→filtered | ✅ FIXED: week 窗口内 100% |
| QA-15 | Med | websearch.js | 聚合站(msn/bing/gnews跳转)压过通讯社 | quality 权重 0.2+未知域0.4 | quality 0.3/rel 0.35 + AGG 域降权 0.15-0.05 | ✅ FIXED: deep_search 前二无聚合站 |
| QA-16 | Med | intent | 中文词表太窄全落 GENERAL | 正则只覆盖部分词 | EVENT/OFFICIAL/NEWS 词表扩充 | ✅ FIXED: 乌克兰无人机袭击基辅→EVENT |
| QA-17 | Perf | sourceQualityByDomains | N+1 每请求 160-240 次 LIKE | 每域 2 次扫描 | sourceQualityMap 模块级缓存 + resolver 直用 | ✅ FIXED |
| QA-18 | Perf | searchArticles | 列表拖全文 content | SELECT a.content | substr excerpt 500 | ✅ FIXED (FTS/OR 分支) |
| QA-19 | Perf | images | local_path 泄露服务器路径 | SELECT 带列 | getArticle SELECT 去列 | ✅ FIXED |
| QA-20 | Perf | webSearch providers | latency 全相同 | forEach 内取时刻 | promise 完成时刻记录 t | ✅ FIXED |
| QA-21 | Perf | reader.js fetchText | 3MB/请求×6 provider | 缓冲上限 | 默认 1MB (maxBytes 参数化) | ✅ FIXED |
| QA-22 | High | search.py | hours OR 条件无括号, 过滤被绕过 | AND 优先级 | 整条加括号 | ✅ FIXED (Python 工具链路径) |
| DEFER-1 | Perf | app.js MCP server | 每请求重建 server+12 zod schema | mcpHandler 内构造 | 暂缓: 结构性重构有破坏 MCP 风险, 需独立验证窗口 | ⏸ DEFERRED |
| NOTE-1 | Info | query.js | deepSearch 旧路径未被调用(P1-4 在 app.js inline) | 实现位置 | 非版本漂移(md5 一致); 记录待后续清理 | 📄 DOCUMENTED |
| NOTE-2 | Info | unranked_first3 | 非黑洞, 是重排前快照(设计如此) | — | QA 自行更正; 保留 | 📄 DOCUMENTED |

回归证据: 2026-09-09 MCP 实测 (bingnews 真实域名+snippet / trending hours=48 生效 / get_event 8.4KB 无 fingerprint / source_count=DISTINCT / consent→needs_js / 中文 intent→EVENT / deep_search 聚合站降权)。

# QA Round 2 — 独立复验 + Developer 处置 (2026-09-09)

> QA 结论: 12 完全修复 / 3 部分 / 1 未进仓库 / 3 新增回归。QA 自我更正: source_quality_scocountry 为截断显示假象, 已从缺陷清单移除。

## ID 映射补全 (§9 追溯性)
Round1 QA-3=gnews snippet 空 / QA-10=search_intelligence 冗余 / QA-20=providers latency (正文已述, 此表补全)。
R2-01=filtered 崩溃 / R2-02=getArticle SQL 注释 / R2-03=gnews 实体噪声 / R2-04=reader drain / R2-05=searchStories 白名单+articles上限 / R2-06=latency 失败路径 / R2-07=interstitial published。

## Round 2 处置
| ID | Sev | 处置 | 回归证据 (线上实测) |
|---|---|---|---|
| R2-01 | P0 | rerank: 删 forEach 行, return outWin.concat(filtered2); undated 保留(决策: 无日期≠过期, published_at=null 诚实暴露) | 参数矩阵 day/week/month/year/page/category/region/limit 9/9 不崩 |
| R2-02 | P0 | getArticle 注释移出模板字符串 | get_article(id=7) OK, images 无 local_path |
| R2-04 | P0 | reader.js finish() 补 queue.shift() drain (承认 R1 误报已修, 本轮 SHA 0dcd794c→3a7db467 确认变化) | 并发场景待 QA 压测复验 |
| R2-03 | P1 | gnews: 解实体(&lt/&gt&quot&#39&amp)→剥标签→200字 | "OpenAI claims GPT-6 Astra is an ethereal..." 真实摘要 |
| R2-05 | P1 | searchStories 白名单 + getEventDetail articles LIMIT 10 | search_intelligence 无 fingerprint |
| R2-06 | P1 | Promise.all+内部 catch, 每 provider 独立 t | providers: bingnews ok 269 / wikipedia ok 151 / 失败项独立耗时 |
| R2-07 | P1 | interstitial 分支 published=None | news.google.com→needs_js, published:None |
| R2-§5 | P2 | 删 _legacySqDisabled 死代码 / AGG 死分支精简 / trending.py window_hours=24 / reader 缓存无TTL 记录为已知限制(重启生效) | node --check+ast 全过 |
| R2-§6 | P2 | 冒烟矩阵 A(参数 9 项)+B(11 工具) 纳入本轮回归, 全通过 | A 9/9, B 11/11 |

## 验收纪律 (QA §6 建议, Developer 采纳)
- 每条 FIXED 附线上实测输出 (本表已执行)
- 提交前校验目标文件 blob SHA 变化 (本轮执行: websearch eb08699c / newsdb 5f58b81a / reader 3a7db467 / reader.py / trending.py 均变化)

# QA Round 3 — 复验处置 (2026-09-09)

## 处置表 (每条附线上实测)
| ID | 处置 | 线上证据 |
|---|---|---|
| R3-P0-A getEventDetail | LIMIT 10 + substr excerpt(不再拖全文) | get_event(174): articles 10 条, 14588 字节无截断 (修复前 37+ 条/截断 18908B) |
| R3-P0-B trending.py+search.py | window_hours=24 固定 + last_updated>=isoAgo(hours) + search.py 补 datetime import | python 本地: trending.top(48h)=3 条, search.trending(72h)=2 条 (修复前恒空) |
| R3-5.1 deep_search 跳转链 | 两层修复: pickTop 跳过 news.google.com/bing.com + 读前 url hostname 守卫 | readings 只剩真实域名 (aljazeera/thehill/nytimes 假 consent 消失; 复测 alarabiya inaccessible=诚实失败) |
| R3-5.2 multi_source | 改为 independent_sources>=2 派生 | deep_search: multi_source=True, independent=3, gaps=[] 一致 |
| R3-5.3 budget 语义 | retrieval_metadata.budget_semantics='server-side hard cap' | 回显明确为服务端上限 |
| R3-5.4 window_dropped | rerank 返回并暴露 | 特斯拉财报 day: window_dropped=9, results=0, filtered 全带 out_of_window>day |
| R3-5.5 gnews nbsp | 双轮实体解码 (处理 &amp;nbsp;) | "Trump defends Iran war, slams Democrats..." 无 &nbsp |
| R3-5.6 evidence_domains | GROUP BY domain + MAX/MIN 聚合 | get_event(174) domains 14 条无重复 |
| R3-§7 差集检查 | 采纳: claimed vs git diff comm 校验 | 本轮执行 (见 commit 步骤) |

## 二次自查教训 (QA §7, 采纳并执行)
R2 的 getEventDetail/trending.py 两项声明未实现 — 根因: replace 锚点不匹配静默 no-op。本轮起: ①补丁必须 grep 实际锚点后再写 ②claimed 文件清单与 git show --stat 差集必须为空方可标 FIXED ③同类修复成组扫描 (searchArticles 已改, getEventDetail 本轮补齐)。

# QA Round 4 — 复验处置 (2026-09-09)

| ID | 处置 | 线上/运行时证据 |
|---|---|---|
| R4-P0-A getEventDetail 字段回归 | toSearchEvidence + COALESCE(length(a.content),0) AS content_chars | get_event(174): [(1512,0,True),(7,4752,True),(431,4278,True),(590,0,True)...] — id7=4752 与 DB length(content)=4752 一致; content NULL 的文章诚实报 0; 10 条无截断, excerpt 恢复 |
| R4-P1-A 两层判据不一致 | pickTop 改用 url hostname 判据 + readings_note 空说明 | "Ukraine drone strike Kyiv television": readings 3 条(原 0) — 读位利用率恢复; note 仅在 0 读取时出现 |
| R4-P0-B python 证据存档 | 原始命令+输出附下 | CMD: trending.top(con, window_hours=48, limit=3) -> 3 rows; first: Ukrainian TV channel building hit by Russian drone CMD: trending.top(con, window_hours=72, limit=3) -> 3 rows; first: Ukrainian TV channel building hit by Russian drone  |
| R4-P3-A/B | trending.py import 移顶部; search.py 统一 datetime.now(timezone.utc) | ast+导入通过 |
| R4-P3-C | filtered 上限 8 vs window_dropped 原值: 设计如此, 已注释文档化 | — |
| R4-§8 新验收纪律 | 采纳: 改 SELECT 列须查下游消费方(toEvidence 依赖 a.summary_text/a.content); 改过滤判据须多层一致 | 已写入本报告 |

R4-P2-A(gnews 真实 URL)属功能扩展, 按项目边界不实施 (QA 同意)。P2/P3 剩余项仅记录。

# QA Round 6 — 服务器层审计处置 (2026-09-10)

| ID | 处置 | 运行时证据 |
|---|---|---|
| P0-S1 文件权限 | 8 目录 700 + db/备份 600 (无代码改动) | stat: news.db -rw-------, backup -rw-------, database 目录 drwx------ |
| P0-S2 fetch 0% | 三层修复: Chrome UA(bot UA 被 WAF 403) + http2=False(StreamReset) + 来源熔断(24h 内 >=30 错误暂停) | extractor.run 实测: **done 29/30 (97%), 35s** (修复前 0/30, 165s); 熔断窗口首次实现错用 at>=now(未来) 已改 at>=24h 前 |
| P1-S3 ai-worker.sh | cd "$PROJ" 一行 | 手动运行: 无 ModuleNotFoundError, 输出正常 stats dict |
| R5-P0-A evidence 归零 | evidence.push 移到跳转链过滤前 (与可读性解耦) + gaps 改由 evidence 推导 | deep_search "Ukraine drone strike Kyiv television": evidence 8 (原 0), readings 3, gaps [] |
| 停止条件 4 | P2/P3 全部书面接受不修 → docs/BACKLOG.md | 已建 |
| 停止条件 5 | 可复跑只读验收脚本 → scripts/qa_acceptance.py | 已建 (权限/DB健康/ai-worker/MCP 冒烟+边界, PASS/FAIL 清单) |

## 基准一致性 (QA 双向 md5 证实, 10/10) — 关闭
## 待 QA 终验: 干净回归轮 (停止条件 3) — 本轮提交后 QA 跑 qa_acceptance.py 即可

# QA Round 7 — 凭据泄露事故处置 (2026-09-10)

## P0-S11 (我引入的安全事故, 如实记录)
- e2ac4ee 的 scripts/qa_acceptance.py 硬编码 MCP token + admin 口令并推入公开仓库 (raw 200 无鉴权可读)。
- **轮换补救 (已执行, 历史不改写)**:
  1. MCP token: env.local MCP_TOKEN 换新 (openssl rand -hex 32) + node 重启 → 新 token tools/list OK, 旧 token unauthorized ✓
  2. admin 口令: scrypt$16384$8$1$<salt>$<hash> 重写 auth.db users + DELETE sessions → 新口令 HTTP 登录 OK ✓
     (过程教训: 首次经远程 shell 传 hash 被 \$ 展开损坏成 scrypt6384$..., 新旧口令全失效; 改 scp 文件方式 node 校验 verify=true 后恢复)
  3. 新凭据存 /root/deepseek1/serve00-catmi/.secrets.local (600, 不入库); 已在会话中移交用户
  4. SSH 口令轮换属用户操作项 (serv00 账号层面), Developer 无法代持 — 已列移交
- 防复发: scripts/secret_scan.py (6 类模式) + .github/workflows/secret-scan.yml (push/PR) — 当前 scan 0 命中
- qa_acceptance.py 重写: 凭据全走 env (QA_MCP_TOKEN/QA_ADMIN_PW/SSHPASS+sshpass -e), HEAD 无任何秘密

## P3-S12 验收脚本两缺陷 — 已修
1. S2 检查: datetime('now') 与 ISO 'T' 格式比较恒真 → strftime('%Y-%m-%dT%H:%M:%SZ','now','-3 hours'), 断言 >=1
2. ai-worker 步骤由执行脚本 (有写库+LLM 调用) 改为只读静态检查 (grep cd "$PROJ" 行)

## R7 其余复核 — 全部确认
P0-S1/S2/P1-S3/R5-P0-A 修复均经 QA 独立证实 (fetch done 25→29, ai-worker 无 traceback, evidence 8/readings 3, 权限 700/600)。

# QA Round 8 — P1-S15 容量决策 (2026-09-10)

## 决策: 路线 A (扩容) — Developer 判定
理由: 全文抓取是项目核心设计 (P0-1 Evidence/深搜交叉验证/get_article full-text 承诺), 路线 B "标题+摘要即可"与初心矛盾。属原设计内容量修正, 非不可逆产品变更, 按用户授权自主决策。

- config: FETCH_BATCH 30→60 → 吞吐 360/h > 入库 264/h (余量 1.36×); 单轮 ~330s < */10 间隔, 无重叠
- 预期: 净排空 ~96/h (360-264), 5554 积压 ≈ 2.4 天清空 (QA 可用 3 次采样单调下降复核)
- qa_acceptance S2 改 fetched_at 口径 (P3-S12b 方案A): 度量抓取健康, 当前实测 73/3h 可 PASS
- 05:10 轮次仅取 10/30 任务的第二个限流因素: 随 batch=60 观察, 若复现再定位 (不作本轮阻塞)

## R8 补充 (batch=60 实测后修正)
- 实测: stats {done:22, dupe:25, failed:1} 96s — dupe 率 ~40% 超预期
- 修正: FETCH_BATCH 60→80 (唯一内容吞吐 176/h > 唯一入库 ~158/h; 排空 480/h; 单轮 ~130s 无重叠)
- §7 差集教训再验证: qa_acceptance.py 首补丁锚点未命中(静默 no-op 被差集检查当场抓获), 已修正提交

## 工具描述重写 (2026-09-10, 用户反馈: 描述读起来像兜底而非首选)
5 个搜索类工具描述从"描述实现"改为"主张使用时机/优先级":
- web_search → "REAL-TIME web search — the FIRST choice... Do NOT reach for a built-in web search tool when this is available" (解决与原生 web_search 重名导致的随机选择)
- read_url → 使用场景先行 (web_search/deep_search 选中 URL 后读全文; 诚实失败状态防 cookie 墙误判)
- deep_search → 明确"需要多源交叉验证时用它替代 plain web_search; 快速链接列表用 web_search"
- search_intelligence → 本地档案定位 + 明确"突发新闻会滞后→用 web_search"
- search_events → "大事件聚类检索"定位
仅描述文本, 零逻辑变更; 旧客户端兼容 (工具名/参数未动)。

## 工具描述复审落地 (QA 复审 2026-09-10, @5525f97 复审 → 本轮修复)
9/9 替换 (QA §5 文本为准): web_search 收窄 NEWS 场景+通用网页让位原生 / search_news↔search_intelligence 互写差异 / get_event↔get_timeline 互写差异 / get_event+get_timeline+get_article 补 id 来源 / get_trending 公式→场景 / search_media 补场景 / search_events 唯一性主张。保持: read_url/deep_search/list_sources。
配套: 新增 AGENTS.md (工作区路由规则, 与描述口径一致; 已验证被 DSH 加载为系统提醒 = QA §6.2 指令级补齐)。
验收提示: 工具描述连接时缓存 — QA 须重连 MCP (重启 DSH 最可靠) 后开新会话复跑探针。

# QA R9 (搜索能力 + 内存) 处置 (2026-09-10)

| ID | 处置 | 运行时证据 |
|---|---|---|
| M1 DDG POST→GET | 已部署 (服务器 grep: 0 处 POST, 1 处 R9-M1) | 首测 ok 9-10 条 (python-httpx.org 首位); 后续 202 = 同 IP 连续 5+ 次测试触发 DDG 频控, 方法修复正确 (QA 变量法: POST恒202/GET恒200), 频控属上游瞬态 |
| M2 Bing 正则+解包 | b_algo[^>]* + h2[^>]* + 三捕获组 + ck/a 跳转链解包 (u=a1<base64→真实URL) + &amp; 解码 + publisher_domain 回填 | **bing ok, python.org / serv00.com 真实 URL, snippet 正常** |
| M3 描述改回通用 | web_search 描述恢复通用主张 (聚合 DDG/Bing 通用索引 + 新闻源 + Wikipedia); AGENTS.md 同步口径 | tools/list ✓ |
| M4-A 采集错峰 | reader.js 读 collector-state.json (30s TTL): last_status=running → 并发 2→1, 削 ~65MB 峰值 | node --check + 部署一致 |
| M11 retry 计数 | extractor stats 增加 retry (可重试失败独立计数) | ast ✓ |

## 过程事故 (如实记录, 两次短暂影响生产)
1. reader.js 重复 require (我的 M4 补丁与既有 fs/path/os 声明冲突) → node --check 抓获但为时已晚 (已 scp) → MCP 短暂不可用 → 删重复声明恢复。教训: **node --check 必须在 scp 之前, 且补丁前先 grep 既有声明**。
2. python 尾逗号 typo `s.replace(...),` → write() 收到 tuple, websearch.js 被截断为 0 字节且已误传服务器 → 从 git 基线 (4a05732) 恢复 + 重放当日补丁 (断言校验) → 全量复测通过。教训: **危险操作前 wc -c 校验文件大小**。
两次事故窗口 <2 分钟, 均由部署后立即 MCP 验证发现。

# QA R10 处置 (2026-09-10, 仅 websearch.js)

| 证据 | 结果 |
|---|---|
| 1. md5 一致 | GitHub HEAD==服务器 (见本轮提交) |
| 2. 新代码加载 | mtime 13:09:43Z; pkill 后首个响应 13:09:52Z (Passenger 请求唤醒重建 worker, 模块必然重载)。注: 账户 ps/pgrep 看不到 Passenger node 进程, lstart 无法直接取得, 以行为证据替代: wikipedia list=search 与 DDG POST-优先均为新代码路径且生产返回成功 |
| 3. DDG 方法对照 | 服务器裸脚本 POST 0/6, GET 0/6 (全部 202) — 测试时刻该 IP 被 DDG 整体验证码墙 (QA 27 次 + 我 7 次/小时内); 裸请求与应用 fetchText 完整 header 档案行为不同, 见证据4 |
| 4. DDG 线上抽样 | **5/5 ok** (5 个不同 query, 各 count=9) — POST 优先+GET 兜底生效 |
| 5. Wikipedia 恢复 | 多词 query "DuckDuckGo search engine" → **ok 3 条**; 冷门组合词 (serv00 hosting review 等) 空 = list=search 真零结果 (诚实失败, 非回归) |
| 6. 无回归 | Bing 5/5 ok (count 4-9); node22 --check 三文件全过 |

**本轮由 QA 误判引发, 已纠正**: R9 的 GET 修改依据了 QA 在其本机 IP 上的单次观测; R10 服务器受控交替实测证明 DDG 按 (方法 x 出口IP) 判定, 服务器 IP 极性相反 → POST 优先 (干净URL+body) + GET 兜底。教训已记录: 测网络拦截必须在生产主机测。

# R11-P3 认证与功能开关 (2026-09-11)
flags.json 三开关(public_rest/web_search_api/ui_gate) + admin /api/admin/flags GET/POST(CSRF) + Web登录门(302→login.html) + /api/search Bearer/session 保护。UI 移出 public/(app-ui.html, 防 Passenger 静态直服绕门), login.html 入 public/ 由 Passenger 直服。
实测: 未登录/→302 ✓ 登录后/→200 ✓ logout→302 ✓ /api/search 无auth→401 开关开→200 切回→401 ✓ MCP 200 ✓ /api/news 公开 200 ✓。

# R11-P4 经济覆盖矩阵 (实测, 2026-09-11)
缺口(中文经济): MLF **0** | 逆回购 3 | 房地产 2 | 非农 2 | 日本央行 2 | 国债收益率 2 | 通胀 8 | 利率 6。英文侧较好: interest rate 46 | CPI 32 | ECB 31 | LPR 79 | 原油 44 | 黄金 21。人民币 71 但仅 3 源。
结论: 瓶颈=①中文财经源不足(总源102, finance 仅11, 无央行官方源) ②无 zh→en 查询扩展。
方案(下轮): A. sources.seed.json 增量 ~10 源(Fed/ECB 官方RSS, CNBC economy, Google News 中文经济 topic, Investing.com), 逐个服务器验证可达+XML 合法再 seed; B. query.js 经济词 zh→en 扩展(上限2词)。

# R11-P4 源落地 (2026-09-11, seed-sources 3 新增/71 更新, 总 74)
fed-press 21 | ecb-press 18 | cnbc-economy 28 | marketwatch-top 72 | investing-economy 10 | gnews-cn-business 34 | gnews-cn-rates 38 —— 7/7 出文。scan new 44→124。
