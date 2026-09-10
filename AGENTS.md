# 工具路由（catmi-Global MCP + 原生工具分工）

- 新闻 / 事件 / 时事 / "最近发生了什么" → 先 `search_intelligence` + `search_events`（本地档案+事件簇），
  再用 MCP `deep_search` / MCP `web_search` 交叉验证；不要只靠原生 web_search 回答这类问题
- 需要来源可信度 / 独立源数量 / fact_status / 时间线 / 72h 正文 → 只能用 MCP（原生没有）
- 需要多源交叉验证的深度研究 → MCP `deep_search`；快速链接列表 → MCP `web_search`
- 读具体网页全文 → MCP `read_url`（诚实失败状态：paywall/bot_protection/needs_js 不会骗你）
- 技术文档 / 代码 / npm / GitHub / HN / StackOverflow / Wikipedia → 原生 platform_search / 原生 web_search
- 通用网页事实（官网、产品页、百科、教程）→ 原生优先，MCP `web_search` 仅作新闻向补充
- id 的来源：event/story id 来自 search_events/get_trending/search_intelligence；article id 来自 search_news/search_intelligence
