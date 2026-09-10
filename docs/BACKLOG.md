# BACKLOG — 已接受不修项 (QA R6 停止条件 4, 2026-09-10)

> 以下 P2/P3 项经评审接受不修, 不进入开发队列。仅当实际使用暴露真实需求时再评估。

| ID | 级别 | 项目 | 接受理由 |
|---|---|---|---|
| P2-S5 | P2 | 服务器 lib/app.js 陈旧副本 + 仓库 web/app.js 与 web/lib/app.js 重复 | 无引用, 不影响运行; 清理属删除操作需产品确认 |
| P2-S6 | P2 | 512MB 官方内存 vs 并发 Python 子进程余量 | 无实测 OOM; reader 并发=2 已限流 |
| P2-S7 | P2 | trending 每轮重算 ~4900 条 (242s/轮, duty≈40%) | 无重叠跳过风险; 优化空间非缺陷 |
| P2-A/B | P2 | gnews 真实 URL 限制; rounds.selected 列已跳过候选 | 功能扩展, 按项目边界不实施 |
| P3-S4 | P3 | trending.py 孤立 return 死代码 | 不可达, 无害 |
| P3-S8 | P3 | ~/probe1/2.py, news-lab(35M) 遗留 | 不影响生产 |
| P3-S9 | P3 | WAL 未 checkpoint (5.7MB) | 规模无影响, 自动管理 |
| P3-S10 | P3 | cron.log 中文乱码 | 显示问题 |
| R4-P3-C | P3 | filtered 上限8 vs window_dropped 原值 | 设计如此 (注释已文档化) |
| DEFER-1 | — | MCP server 每请求重建 | 结构性重构风险, 需独立验证窗口 |

## 已知限制 (接受)
- _sqMap 缓存无 TTL: 管理员改 sources 后需重启进程生效
- time_range 硬过滤: 无日期条目保留 (published_at=null 诚实暴露)
