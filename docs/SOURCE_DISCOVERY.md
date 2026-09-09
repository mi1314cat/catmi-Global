# SOURCE_DISCOVERY — 来源发现机制（Source Intelligence Pipeline）

> 原则: **发现 ≠ 启用**。新来源一律先进 `candidate_sources`（verification_status=pending）,
> 通过 抓取测试→内容分析→质量评分→重复检测→审核 五关后才进正式 sources。
> 全流程规则实现, **不依赖任何 AI API**（AI OFF 时发现/验证/评分照常工作）。

## 1. 流水线

```
搜索发现(地区×领域×语言×类型 矩阵)
   ↓  scripts/discover-sources.py --add
candidate_sources (verification_status=pending)
   ↓  probe: HTTP 状态/条目数/feed 有效性 → probe_json
   ↓  内容分析: 语言检测/正文比例/更新频率
   ↓  score_source() 0-100 (docs/SOURCE_QUALITY.md 规则)
   ↓  重复检测: domain/canonical/标题归一化相似度 → 指向已收录源则 reject
   ↓  审核门: score>=60 且 非重复 且 非内容农场特征
verified → 运营启用 (INSERT sources, verification_status=active)
不达标 → rejected (保留记录与理由)
```

## 2. 发现矩阵（搜索_query 模板）
`{region} × {domain} × {language} × {source_type}`，例如:
- `Japan semiconductor news RSS` / `Korea technology news RSS`
- `India business news RSS` / `Southeast Asia geopolitics RSS`
- `Middle East energy news RSS` / `Africa technology news RSS`
- `Latin America economy RSS` / `European cybersecurity RSS`
- `central bank press release RSS` / `statistics bureau RSS`
- 优先结构化: RSS > Atom > sitemap > API > newsletter 归档

## 3. 内容农场/垃圾源拒绝特征（任一命中即 reject）
- 无明确出处/作者/日期; 标题党占比高（标题与正文相似度低）
- 每小时发文 > 50 且正文极短（<200 字符占比 > 60%）
- 全站转载（与已有源标题归一化重合率 > 70%）
- feed 里混入 affiliate/SEO 关键词堆砌

## 4. 与现有系统的关系
- candidate_sources 不进采集调度（scheduler 只读 sources 表）
- 启用走 sourcesvc.seed 同一结构（slug/kind/feed_url/category/language/country/priority/poll_seconds/source_type/tier）
- 生命周期: candidate → verified → active → degraded → disabled → rejected（历史保留）

## 5. 定期运行
- 手动: `python -m news.newsctl discover ...`（后续版本）
- 未来可挂 cron 每周一次, 发现结果永远先进 pending, 人工/规则审核后启用
