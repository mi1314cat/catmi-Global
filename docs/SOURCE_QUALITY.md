# SOURCE_QUALITY — 来源质量评分规则（可解释, 非黑盒）

> 每个来源一个 `quality_score` 0-100，由 5 个分项组成（各 0-20），全部**规则计算**，无 AI 参与。
> 评分伴随 `components` 明细存储，任何分数都可以追溯到具体规则。

## 分项规则（各 0-20 分）

| 分项 | 得分规则 |
|---|---|
| **authority** 权威性 | tier A（官方/通讯社/科研/监管）=20；tier B（专业/地区主流媒体）=14；tier C（社区/社交/博客）=6 |
| **independence** 独立性 | 独立运营、非单一集团连锁=20；属于大型媒体集团=12；已知聚合/转载为主=4 |
| **original_reporting** 原创度 | 有原创报道（非转载聚合）=20；混合=12；纯聚合/无署名=4 |
| **update_frequency** 更新频率 | feed 实测 24h 内有更新=20；3 天内=12；7 天内=6；更久=0 |
| **technical_reliability** 技术可靠性 | probe HTTP 200 且条目≥20=20；条目≥5=14；间歇可用=6；不可用=0 |

## 总分与门槛

- `quality_score = authority + independence + original_reporting + update_frequency + technical_reliability`
- **≥60** 才有资格从 candidate 晋级 review（人工/规则审核）
- **<60** 直接 rejected（保留记录与理由）
- 40-59 分但战略价值高（如小语种独家地区覆盖）可人工特批进 review，须注明理由

## source_type → tier 映射

| Tier | source_type |
|---|---|
| **A**（一手/权威） | official, government, regulator, central_bank, research, statistics |
| **B**（专业媒体） | wire_service, professional_media, regional_media, financial, corporate, legal |
| **C**（信号源） | community, social, video, podcast, blog |

**Tier C 永不计入事件独立事实来源**（independent_source_count 排除 C），仅作趋势/线索信号。

## 使用位置

- 来源入库时打分（`sourcesvc.backfill` / `discover-sources.py`）
- 审计报告按分数段统计（`scripts/check-sources.py`）
- 事件证据中权威来源优先展示（official > wire > regional > community）
