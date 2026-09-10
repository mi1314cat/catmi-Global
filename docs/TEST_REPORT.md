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
