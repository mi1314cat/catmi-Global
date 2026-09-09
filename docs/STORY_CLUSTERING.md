# STORY_CLUSTERING — 事件聚类设计（Phase 3）

> 目标: 不同媒体报道同一事件 → Story #N（保留全部来源），不依赖 LLM。
> 已验证参照: Pharos（指纹+锚点 Jaccard, 专有 license 只借设计）、Heatwire（72h 窗+seed-guard）、
> MuckScraper（三级级联: 词元→向量→LLM 仲裁——本系统只用第①级 + 专名锚点，向量/LLM 留作可选增强）。

## 1. 算法（news/stories.py v2）

每篇文章生成两组信号：

**锚点 anchors（强信号, 决定归并）** — `e:` 命名空间：
- 专名短语: 连续大写词 2-4 个 → `e:donald_trump`, `e:west_bank`, `e:canada`
- 缩略词: 全大写 2-5 字母 → `e:us`, `e:nato`, `e:eu`, `e:fbi`
- 句中大写单词（宽容提取, 靠窗口+阈值滤噪）
- 来源: 标题 + RSS 摘要头 400 字 + 正文头 1500 字（未抓正文的 discovered 文章也有标题+摘要）

**词元 tokens（弱信号, 兜底归并）** — `t:`标题词元 / `d:`发布者域 / `w:`正文前 30 词

判定（先到先用, 记录依据）：
```
anchor_containment = |A∩B| / min(|A|,|B|)   ≥ 0.5  → 归并 (method=anchor:0.xx)
title_jaccard(标题词元)                       ≥ 0.30 → 归并 (method=title:0.xx)
约束: category 一致（跨类不聚）+ |article_time − story.last_updated| ≤ 72h
```

containment（非对称）比 Jaccard 对标题长短更鲁棒：路透长标题 vs 唧唧短标题仍可命中共同实体。

## 2. 实测调参记录

| 版本 | 算法 | 实测（Google News WORLD 批量, 跨源同事件） | 结论 |
|---|---|---|---|
| v1 | 纯标题词元锚点(t:/d:) Jaccard≥0.30 | 25 篇仅归并 1 篇（DW/BBC 加拿大贸易战未聚上） | ❌ 跨源措辞差异大 |
| v1.5 | gnn 独立测试: 词元 Jaccard 0.30 | 92 条 → 4 个多源簇 | 方向对但召回低 |
| **v2** | **专名锚点 containment≥0.5 或标题 Jaccard≥0.30** | 见 TEST_REPORT（预期: US/Canada/Trump 共享 → 归并） | ✅ 主通道 |

灰区(0.30-0.50 containment)留给可选 LLM 仲裁（AI Provider 打开时旁路写入, 不影响主链）。

## 3. Story 生命周期
- 创建: 首篇进窗（first_seen=文章时间）
- 更新: 每次归并 last_updated=now, 指纹并集**只增不减**（质心防漂移的保守替代, 简单可靠）
- 计数: article_count / source_count(独立源) / video_count —— SQL 子查询实时重算
- 归档: 30d 无更新 → status=archived（保留检索）; bookmarks 可钉住
- 热度: trending.py — `heat = Σ_独立源 best(priority × exp(−age_h/30h))`, 24h 窗,
  importance: ≥6 major / ≥3 high / ≥1.2 normal / else low（Heatwire 公式, 纯 Python+SQL）

## 4. 可解释性
- story_articles.method/score 每次归并留痕（UI/API 可展示"为什么聚在一起"）
- stories.fingerprint 保留 anchors+tokens 全集（审计/调试）
- entities/locations 列预留: Phase 4+ 用确定性规则（专名表→国家/城市映射）填充；AI 可增强

## 5. 已知边界（诚实声明）
1. 同名实体冲突（两个 "Johnson"）会误聚 → 靠 window+category 缓解; 后续可加 domains 差异惩罚
2. 换称谓（"Biden" vs "the US president"）漏聚 → 标题通道兜底部分场景; 灰区仲裁是正解
3. 非英语标题词元分词弱 → 锚点通道(专名)基本语言无关; 中文标题无大写锚点 → 依赖 w:词元 + Jaccard,
   中文场景建议开 AI Provider 或配 gnews-zh 的 GNews 原生聚簇参考
4. 单篇孤立事件 → 独立 Story（正常语义）
