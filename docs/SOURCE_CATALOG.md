# SOURCE_CATALOG — 来源总目录与审计（可再生: scripts/check-sources.py）

> 统计生成时间: 2026-09-09 · 数据源: news-data/state/source-audit.json (每轮审计自动更新)

## 总量
| 项 | 数 |
|---|---|
| 正式来源 | **74**（全部 active, verification_status=active） |
| 候选池 candidate_sources | 48（**pending 28 / rejected 20**——绝不未审先采） |
| 事件证据 | 400 active stories 已重建（OFFICIAL_CONFIRMED 76 / CORROBORATED 9 / SINGLE_SOURCE 295 / UNVERIFIED 20） |
| 质量均分 | 73.4 / 100 |

## Tier / 类型分布
| Tier | 数 | 说明 |
|---|---|---|
| A（一手/权威） | 18 | WHO/UN/NASA/Nature/Science/Agência Brasil + Reuters/BBC/NHK/TASS/DW/AlJazeera/CNA/Yonhap 等通讯社 |
| B（专业/地区主流） | 52 | 专业媒体/地区主流/财经 |
| C（信号源, 不作事实确认） | 4 | Hacker News/Reddit r/books/Phoronix/Krebs |
| 类型 | regional_media 52 · wire_service 16 · community 4 · official 2 | |

## 地区/语言/领域
- 国家: US 8 · CN 3 · RU 2 · JP 2 · IN 2 · HK 2 · TW 1 · KR 1 · GB 1 · 其余为国际/聚合源（52 标 "-"——下一阶段补 country 字段细化）
- 语言: en 61 · zh 9 · ja 2 · ko 1 · fr 1（候选池再含 vi/pt）
- 领域: general 24 · tech 21 · finance 11 · geopolitics 8 · video 5 · life 2 · society/fiction/business 各 1

## 健康
- degraded 标记: 1（只标不删, disabled_reason 记录原因, 可恢复）
- 24h 采集错误: 1200 条（多源重试产生, cleanup/72h 窗口管理）

## 候选池发现结果（首轮 48 候选）
- 通过: 28（Guardian/AlJazeera/DW/France24/Euronews/CNN/PoliticoEU/CNA/Nikkei/JapanTimes/TaipeiTimes/KoreaHerald/NDTV/IndianExpress/Dawn/BangkokPost/VnExpress/Inquirer/TimesOfIsrael/AllAfrica/MercoPress/AgênciaBrasil/MexicoNews/Meduza/MoscowTimes/KyivIndependent/ABC-AU/SixthTone + HN/LWN/IT之家/Nature/Science/PhysOrg/Quanta/CNBC/MarketWatch/OilPrice/CoinDesk/DefenseNews/SpaceNews…）
- 拒绝: 20（probe 失败/域名重复——如 UN News 与已收录源重复; 保留记录不启用）
