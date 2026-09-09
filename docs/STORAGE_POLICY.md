# STORAGE_POLICY — 存储分层与滚动清理

> 实现: news/retention.py（cleanup 命令）+ config 保留参数 + 磁盘水位门（du -sk 实测）
> 容量基线: 3GB 配额；当前占用 130M（含 venv/代码/库）——数据库+图片+缓存远低于阈值

## 1. 三层时间窗（全部是 config 项, 不硬编码）

| 层 | 窗口 | 内容 | 落地 |
|---|---|---|---|
| 短期 | **72h** | 文章正文（articles.content）+ 图片文件（本地）+ 原始页缓存 | purge_content / purge_images / purge_raw_cache |
| 中期 | 30d | 元数据（标题/URL/作者/类别/摘要/事件关联）→ 文章元数据永久保留 | archive_stories（30d 不活动→archived） |
| 长期 | 90d | Story 时间线/计数/指纹（status=archived 保留检索） | 无删除操作（bookmarks 钉住不受影响） |

config: RETENTION_CONTENT_H=72, RETENTION_IMAGES_H=72, RETENTION_RAW_H=24,
RETENTION_METADATA_D=30(归档线), RETENTION_STORY_D=90(远期), ERRORS_D=14, TASKS_D=7

## 2. 清理动作明细
- `purge_raw_cache`: 删 CACHE/date/ 下 >24h 的 gz 文件
- `purge_content`: content 超 72h → 置 NULL, status='purged', **FTS5 行同步 DELETE**（检索仍可用标题 LIKE）
- `purge_images`: 图片行超 72h → 删本地文件, local_path=NULL, purged_at 记录（URL 元数据保留）
- `archive_stories`: last_updated >30d → status='archived'（列表默认过滤, /api/stories?include 可选）
- `purge_tasks_errors`: done 任务 >7d、错误行 >14d

## 3. 磁盘保护四档（images.py / newsctl run 前置检查）

| 档位 | 判定（du -sk ~/ vs 3GB） | 行为 |
|---|---|---|
| normal | <50% (<1.5GB) | 全功能 |
| warning | ≥50% | **新图片下载跳过**（只存 URL 元数据） |
| high | ≥70% | 立即执行过期清理 + 持续跳图片 + 抓取批次减半 |
| emergency | ≥85% | **管道只做清理**（run→cleanup-only）+ 正文/图片全量立清（hours=0） |

- `cleanup --emergency` 手动强制；`newsctl run` 自动按水位降级（写入 last_run meta 可查）
- 绝不因磁盘爆满 crash DB：所有删除走 SQL 批量 + WAL 检查点

## 4. 数据库文件治理
- WAL 模式：管道写/服务读并发；doctor 检查 wal 字节数（>50MB 提示 checkpoint）
- backup：SQLite backup API（一致性快照）→ news-backups/news-*.db.gz 保留 7 份（约 5-20MB/份）
- restore：解压→替换 news.db→管道队列自动续跑（无状态设计）

## 5. 增长预估（49 源基线）
- 文章：~1100 条/天峰值新发现（含跨源重复 ~40%）→ 元数据 ~200KB/天
- 正文：仅提取成功入 72h 窗，稳态 ~55-200 篇在线正文 ≈ 1-4MB
- 图片：12-40 张/天 × ~60KB ≈ 2-4MB/天，72h 稳态 <10MB
- 结论：稳态磁盘占用 <200M（数据库+图片+备份）——3GB 配额余量 >90%
