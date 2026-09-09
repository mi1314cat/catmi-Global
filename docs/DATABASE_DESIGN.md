# DATABASE_DESIGN — news.db (SQLite, WAL, FTS5)

> 版本: schema v1 · 实测: sqlite 3.50.2, FTS5 可用 · 路径: `~/news-project/news-data/database/news.db`
> 原则: 单库多读单写（WAL）；管道写 / Node 服务读；无 PG/Redis/ES。

## 表结构（news/schema.sql）

### sources — 源注册表
| 列 | 说明 |
|---|---|
| slug(UNIQUE)/name | 标识 |
| kind | rss \| gnews \| sitemap \| api \| gdelt \| page |
| adapter | kind=api 时的 JSON 适配器名（hn_algolia/bilibili_popular） |
| feed_url/site_url | 端点（全部实测 200 才入库；来源见 SOURCE_STRATEGY.md） |
| category | general/tech/finance/geopolitics/society/video（general 时按标题启发式归类） |
| language/country/priority | priority 参与 heat 计算（0.6–1.5） |
| poll_seconds | 分片轮询间隔（600–21600；P0=600-900, P1=1800-3600, P2=7200-21600） |
| etag/last_modified/last_fetch_at/last_ok_at | 条件 GET 状态 |
| consecutive_failures/disabled/disabled_reason | 5 连败自动停用（可 seed 重置） |

### articles — 文章
id, source_id, url(UNIQUE), canonical_url, original_title, title, author,
summary_text(RSS 摘要, 兜底素材), published_at(源时间), discovered_at, fetched_at,
**content(正文, 72h 后置 NULL)**, raw_path(原始页 gz, 72h), content_hash,
language, category, story_id, image_main_url, dupe_of, status, extract_method, error

status 状态机: `discovered → fetched → extracted | noextract | failed | dupe | purged`
- dupe: canonical/content_hash 命中既有篇 → dupe_of 指向保留篇（列表查询排除）
- purged: 72h 滚动后正文清空（标题/元数据/关联全保留）
- extract_method: trafilatura / scrapling_fallback / rss_summary / meta_only(视频)

### images
article_id, original_url, local_path(72h 后置 NULL+删文件), content_hash(UNIQUE 去重),
bytes/width/height/mime, main, downloaded_at, purged_at

### stories / story_articles — 事件层（核心）
- stories: title, first_seen, last_updated, heat, importance(low/normal/high/major),
  category, language, **fingerprint(JSON: anchors+tokens)**, entities/locations(JSON, 预留),
  article_count, source_count, video_count, status(active/archived)
- story_articles(story_id, article_id UNIQUE, method, score, joined_at) — 多对多归并记录，
  method 如 `anchor:0.57` / `title:0.33` / `seed`（可解释聚类）
- 算法: 见 STORY_CLUSTERING.md

### tags / article_tags — 标签（Phase 4+: 确定性规则标签; AI 可增强）
### crawl_tasks — 断点队列
kind(article/image/feed/api), state(pending/running/done/failed/skipped), attempts,
next_attempt_at(1h/4h/12h 退避), last_error —— running>1h 判 stuck（doctor 报告）
### crawl_errors — 失败日志（保留 14d）
### trending — story_id, score, window_hours, computed_at（heat 快照, 每轮重算 24h 窗）
### bookmarks — kind(article/story), ref_id, note（用户收藏, 不参与清理）
### articles_fts / stories_fts — FTS5 虚拟表, rowid=article/story id
- 提取成功后 DELETE+INSERT（FTS5 不支持 UPSERT —— 实测教训）
- 正文 purged 时同步 DELETE 行（元数据仍可用 title LIKE 检索）

## 索引
articles: status+discovered, discovered DESC, story_id, canonical_url, content_hash, published DESC
sources: disabled+last_fetch_at; stories: last_updated DESC, status+last_updated;
tasks: state+next_attempt_at, article_id; images: article_id, content_hash(UNIQUE partial)

## 保留策略与磁盘保护（STORAGE_POLICY.md 的数据面）

| 水位 | 行为 |
|---|---|
| normal <50% | 全功能 |
| warn ≥50% | 新图片下载跳过（meta 只存 URL） |
| high ≥70% | 立即清过期正文/图片 + 停图片 + 抓取频率减半 |
| emergency ≥85% | 管道只做清理；正文/图片全部立清；元数据永保 |

## 备份/恢复
`newsctl backup`: SQLite backup API → `~/news-backups/news-YYYYmmdd-HHMM.db.gz`（保留 7 份）
`restore`: 解压 → 替换 news.db → 管道无状态恢复（队列自动续跑）
