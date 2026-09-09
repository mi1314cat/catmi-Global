# GITHUB_LICENSES — 候选项目许可证核查

> 核查日期: 2026-09-09 · 原则: **"借鉴思路" ≠ "复制代码"**。凡写入我们仓库的代码必须来自许可证允许的项目。
> 标注 `SPDX` 为 GitHub API 识别结果；标注 ⚠︎ 为未在本次核查中独立确认，复用前必须重新核查。

## 许可证矩阵

| 项目 | License（核查结果） | SPDX | 我们能否复制代码 | 风险备注 |
|---|---|---|---|---|
| Scrapling | BSD-3-Clause（源码 LICENSE） | BSD-3-Clause | ✅ 可以（保留版权声明） | 最宽松；0.4.x API 有破坏性变更，锁定版本 |
| Crawl4AI | Apache-2.0 | Apache-2.0 | ✅ 法律上可以（NOTICE 义务） | PyPI 要求署名徽章；反正 FreeBSD 不可运行，不会复制 |
| MuckScraper (grregis) | LICENSE 文件=MIT 文本 | **NOASSERTION** | ⚠️ 需作者确认 | GitHub 无法自动识别；若开源本系统需先取得明确授权 |
| MuckScraper-v2 (starkSV) | 同上（fork） | NOASSERTION | ⚠️ 同上 | 仅借设计，零复制 |
| Heatwire | MIT（GitHub 核实） | MIT | ✅ 可以（heat 公式等可参考实现） | 商标/名称被明确排除在 license 外 |
| Pharos | **专有 "Pharos Proprietary License v1.1"** | NOASSERTION | ❌ **禁止复制** | pyproject 自标 MIT 与 LICENSE 矛盾 → 以 LICENSE 文件为准：仅允许个人查看/修改/自托管；只借鉴设计 |
| qianqiuqiu/news-aggregator | MIT | MIT | ✅ 可以 | 依赖极简，移植参考价值大 |
| Cruxwire | MIT | MIT | ✅ 可以 | 亲和/味觉公式可借 |
| Beehive | MIT | MIT | ✅ 可以 | votes→few-shot 环可近原样实现 |
| Evening News | **无 LICENSE** | null | ❌ **默认保留所有权利，禁止复制** | 只借鉴设计模式 |
| morss | AGPL-3.0（README 自述） | ⚠︎ | ⚠️ 仅借设计 | AGPL 传染性：若复用代码，我们整个系统需 AGPL——不采用 |
| news-please | ⚠︎ 未核查 | - | 复用前核查 | 仅作为提取层 API 设计参考 |
| changedetection.io | ⚠︎ 未核查 | - | 复用前核查 | 参考其 feedparser+SQLite 用法 |
| ftr-site-config | ⚠︎ 未核查 | - | 复用前核查 | 站点规则文件本身有独立授权说明，引用规则前必须查 |
| finviz-crawler | ⚠︎ 未核查 | - | 仅借模式 | 并发/退避/浏览器管理经验 |

## 对本项目的约束结论

1. **可直接复用代码的白名单**：Scrapling（BSD-3）、Heatwire / news-aggregator / Cruxwire / Beehive（MIT）——复制时保留版权与许可声明。
2. **只借鉴设计（禁止复制代码）**：Pharos（专有）、Evening News（无 license）、morss（AGPL）、MuckScraper（SPDX 不明）。
3. **我们项目的推荐策略**：自研为主 + 借鉴设计；需要复制时仅从 MIT/BSD 白名单取小片段并记录出处（在文件头注释标明来源与许可）。
4. **若未来开源本系统**：选 MIT 或 Apache-2.0 均可与上述白名单兼容；避免引入 GPL/AGPL 依赖。
