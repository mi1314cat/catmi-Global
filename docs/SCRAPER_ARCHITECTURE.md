# SCRAPER_ARCHITECTURE — 新闻采集系统架构设计（基于实测）

> 状态: 设计定稿（等待用户确认后进入实现）· 所有组件均经 Serve00 实测或上游证据排除

## 1. 最终架构

```
                 Cron (每 10-15 分钟, one-shot, 串行)
                          │
                 ┌────────▼────────┐
                 │  Feed Scanner   │  feedparser + 条件GET(etag/modified)
                 │  sources 表     │  失败计数→退避→连续N次自动停用
                 └────────┬────────┘
                          │ 新文章 URL 队列 (articles.status=pending)
                 ┌────────▼────────┐
                 │  Fetch Strategy │  ← 本机实测: HTTP-only
                 └────────┬────────┘
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
  S1 RSS 摘要兜底   S2 httpx 抓取       S4 站点规则(sites/*.py)
  (full_text失败时)  (UA合规/超时20s/     (XHR/JSON接口/专用选择器,
                     重试3次退避2/5s)     JS重度站点替代方案)
                          │
                 ┌────────▼────────┐
                 │ Article Extractor│
                 │ trafilatura 主力  │
                 │ → Scrapling p-text│
                 │ → RSS summary     │
                 │ 结构有效性校验     │
                 └────────┬────────┘
                 ┌────────▼────────┐
                 │ Image Extractor  │ og:image→twitter→JSON-LD→srcset/figure
                 │ 评分过滤→下载≤8MB │ → content_hash 去重
                 └────────┬────────┘
                 ┌────────▼────────┐
                 │ Dedup            │ URL规范(canonical+去utm) / sha256内容
                 │                  │ 标题词元Jaccard≥0.8 近重复
                 └────────┬────────┘
                 ┌────────▼────────┐
                 │ Story Clustering │ 指纹=命名空间词元(t:/d:/w:)
                 │ (已实测:92条→19簇) │ 锚点Jaccard≥0.30, ±72h窗, 可解释
                 └────────┬────────┘
                 ┌────────▼────────┐
                 │ AI Pipeline      │ OpenAI兼容 API(远端)
                 │ 摘要/分类/实体/    │ 批处理+熔断(3连败跳过)
                 │ 重要性/story辅助   │ 原文永不覆盖
                 └────────┬────────┘
                 ┌────────▼────────┐
                 │ SQLite (WAL+FTS5)│ articles/images/stories/sources/
                 │ news-data/       │ tags/crawl_errors/ai_results/votes
                 └────────┬────────┘
                 ┌────────▼────────┐
                 │ Web Dashboard    │ 红线: 不得挤占采集资源
                 └─────────────────┘
```

## 2. 目录结构

```
~/news-project/
├── serve00-init.sh  README.md  INIT_*.md  env.example  .init-manifest
├── news-data/{articles,images/YYYY/MM,database/news.db,cache,logs}
├── sites/           # 站点适配器: default.py + 逐站规则(域名→选择器/XHR)
├── venv/            # Python 3.11 (scrapling 0.4.15 + trafilatura 2.2.0 + httpx + feedparser)
└── (实现阶段新增: newscli.py, pipeline/, ai/, web/)
~/news-lab/          # 实验室(保留, 用于未来组件验证)
```

## 3. 关键机制（全部有实测/生态依据）

### 3.1 Fetch Strategy（自动选择，绝不默认起浏览器）
1. RSS 有全文 → 直接用（S1，零成本）
2. HTTP 抓取 → trafilatura 有效性校验（正文≥200字符+标题存在）→ 成功即完成（S2，覆盖 ~90% 新闻站）
3. 失败 → 该域名 sites/<domain>.py 专用规则（XHR/JSON 接口优先）（S4）
4. 仍失败 → 记录 crawl_errors，该文标记 failed（**不崩溃、不无限重试**）
5. （未来可选，默认关闭）S5 外部渲染服务：远端 CDP/自建 Linux VPS 的 Crawl4AI API —— 本机只发 HTTP 取渲染结果

### 3.2 重试与降级（实测 + 生态共识）
- 重试: 3 次上限，退避 2s/5s（生产扩展为 1h/4h/12h 落库式重试），403/429/5xx/timeout 触发
- 每源 error_count++；连续 N 次(默认 5)失败 → sources.disabled=1 + 报告（Heatwire/IT_News 模式）
- 降级链的每一级结果都记录 method 字段（trafilatura/scrapling_fallback/rss_summary）

### 3.3 去重
- Article Dedup: URL 规范化(小写host、去 utm_*、尾斜杠) + sha256(content) + 标题词元 Jaccard≥0.8
- Image Dedup: URL hash + content_hash（sha256），pHash 暂不引入（避免重依赖）

### 3.4 Story Clustering（已实测 92 条→19 簇/0.001s）
- 指纹 = `t:`(标题词) + `d:`(域名) + `w:`(正文前 40 词)，锚点 Jaccard ≥0.30 归组
- ±72h 时间窗 + 单域名成员上限防巨型簇（Heatwire seed-guard 思路）
- 灰区(0.25-0.30)留给 LLM 仲裁（MuckScraper 级联第③级，可选启用）
- 每次归并保存 shared_tokens → Web 端可解释展示

### 3.5 AI（远端 OpenAI-compatible，本机零模型）
- 触发: 仅对新 Story + 未处理文章批处理；JSON schema 输出 + pydantic 校验
- 任务: 摘要/分类(多标签)/实体/重要程度/story 辅助仲裁
- **votes→few-shot 反馈环**（Beehive 模式, MIT）: 用户纠正分类→votes 表→下一轮 prompt 注入 ≤15+≤15 样例
- 熔断: 连续 3 次 API 失败 → 跳过本轮 AI，数据照常入库（AI 是增强不是依赖）
- key 运行时从 env.local 读，不入库不入 Git

### 3.6 资源保护（硬编码在配置）
| 项 | 值 |
|---|---|
| 并发 | 1（串行）+ 域名延迟 1.5s（生产可升 2） |
| 单批文章 | ≤20/cron 轮 |
| 请求超时 | 20s（×3 重试） |
| 图片 | ≤8MB、HTTP HEAD 预检 content-type、<3KB 丢弃 |
| 正文 | ≤200KB/篇入库截断 |
| 磁盘阈值 | 80% → 暂停图片下载，只保留文字 |
| 内存 | 单次运行峰值实测 ≤105MB（限额 512MB） |
| 进程 | cron one-shot 退出（不常驻）；Web 服务如需常驻单独评估 |

## 4. 数据库 schema（阶段2原型已建表验证）

见 pipeline_prototype.py（sources/articles/images/stories/crawl_errors 已实测）。
实现阶段扩展: tags、article_tags、ai_results、votes、feeds(etag/modified)。
统一: 原文永不被 AI 覆盖；source/original_url/published_at 永久保存。

## 5. 与"大杂烩"的边界（明确不做）

- 不引入: PostgreSQL、Meilisearch、Redis、Ollama、任何本地 LLM、Chromium/Playwright、Docker、Next.js、Celery、消息队列
- 组件总数: **Python 4 库（httpx/feedparser/trafilatura/scrapling）+ SQLite + cron + 1 个外部 AI API**
