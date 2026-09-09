# SCRAPER_BENCHMARK — Serve00 实测性能报告

> 测试时间: 2026-09-09 04:27–04:57 CEST · 主机: s12.serv00.com (FreeBSD 14.3, Python 3.11.13, 限额 512MB/20进程)
> 原始数据: 服务器 `~/news-lab/results/`（install_report.txt / *.out / benchmark_data.json / prototype.db）
> 本地副本: `serve00-catmi/news-lab/`（脚本）· 所有结论均有服务器实测输出支撑

## 1. 安装难度（真实 pip 结果）

| 组件 | 结果 | 证据 |
|---|---|---|
| scrapling（解析层） | ✅ **成功**（lxml 6.1.3 源码编译 ~10min + orjson 3.12.0 Rust 编译 ~4min + 纯 Python 包） | `Successfully installed scrapling-0.4.15`，`import scrapling; Selector OK` |
| orjson（Rust C 扩展） | ✅ 成功（`CARGO_BUILD_JOBS=2` 绕开 20 进程上限；默认并行 24 会撞限） | 生成 `orjson-3.12.0-cp311-freebsd_14_3_release_p18_amd64.whl` |
| msgspec（C 扩展） | ✅ 成功（~1min） | `Successfully installed msgspec-0.21.1` |
| curl_cffi（Scrapling 的 HTTP 引擎） | ❌ **上游代码拒绝 FreeBSD** | `curl_cffi/scripts/build.py detect_arch() → Exception: Unsupported arch: system='FreeBSD'`（两次独立触发） |
| playwright | ❌ **PyPI 无任何可装版本** | `ERROR: Could not find a version that satisfies the requirement playwright (from versions: none)` |
| crawl4ai | ❌ 级联失败（硬依赖 playwright + litellm 需源码构建） | `No module named 'playwright'`；litellm sdist build 未完成即超时 |
| trafilatura | ✅ 成功（2.2.0，依赖被 lxml 满足） | `trafilatura 2.2.0`，BBC 真实页面提取 3921 字符 |
| feedparser / httpx / bs4 | ✅ 系统预装（6.0.11 / 0.28.1 / 4.13.4） | 系统包清单 |

## 2. 性能实测（单进程）

| 指标 | 实测值 | 备注 |
|---|---|---|
| httpx 抓取（普通页） | 0.13–0.53 s/页 | 226KB BBC 页 0.34s |
| trafilatura 正文提取 | 0.23–0.25 s/页 | 含元数据 JSON 模式 |
| Scrapling Selector 解析（79 元素页） | <0.01 s | 官方基准（5000 元素 1.99ms）与本机一致量级 |
| 跨源聚类（92 标题 → 19 簇） | **0.001 s** | 词元指纹 Jaccard，纯 Python |
| **端到端原型**（RSS 发现→5 篇抓取→5 正文→5 主图下载→去重→聚类→SQLite） | **11.4 s**，峰值 RSS **87 MB** | 全串行+域名礼貌延迟 1.5s |
| 各阶段峰值 RSS | 解析 33MB / 提取 105MB / 原型 87MB / 自适应 56MB | 全部 « 512MB 限额 ✅ |

## 3. 能力对比（实测勾选，非 README 转述）

| 项目 | Scrapling(解析层) | Scrapling(Fetcher) | httpx+trafilatura | Crawl4AI |
|---|---|---|---|---|
| Serve00 安装 | ✅ | ❌ curl_cffi 拒绝 | ✅ 零成本 | ❌ 无法安装 |
| 普通网页抓取 | （引擎缺） | ❌ | ✅ 0.13-0.53s | - |
| 正文提取 | ✅ markdown/p-text 兜底 | - | ✅ **主力**（含标题/作者/日期元数据） | - |
| 图片提取 | 部分（自写正则/选择器） | - | ✅ 自写（og/jsonld/srcset/过滤/评分） | - |
| 自适应元素重定位 | ✅ save/retrieve/relocate 实测 PASS（56MB） | - | ✗（需自建站点规则表） | - |
| JS 重度页面 | ❌（浏览器层 FreeBSD 不可用） | ❌ | ❌（HTTP-only 拿不到） | ❌ 无法安装 |
| 峰值内存 | 33–105MB | - | 87–105MB | （预估 >500MB，未能在本机验证） |
| Serve00 适合度 | **✅ 主力解析层** | ❌ | **✅ 主力抓取层** | ❌ 明确放弃 |

## 4. 关键实测教训

1. **Wikipedia 对通用 UA 返回 403**（html_len=141）——新闻 UA 策略要用描述性 UA（`NewsResearchBot/0.1 (contact)`），BBC/NPR/Google News 全部接受。
2. **feeds.bbci.co.uk 对 HEAD 返回 404 但 GET 正常**——重试逻辑不要依赖 HEAD 探测 RSS 可用性。
3. **pip 源码编译在 20 进程上限下必须限并发**：`CARGO_BUILD_JOBS=2 MAKEFLAGS=-j2`；默认并行 24 会挂起。
4. **pip 的外层 `timeout` 杀不干净子进程树**（cargo/cc 存活持管道）——服务器侧编译任务用 nohup+轮询模式而非 timeout 管道。
5. BBC 404 页也能被 trafilatura 提取出 3921 字符 → 生产管道必须用**结构有效性校验**（正文长度阈值+标题存在性），否则会把错误页当文章入库。
6. Google News RSS 的 `<source url>` 域名可直接用于跨源聚类，不必抓全文（92 条 → 4 个多来源簇，覆盖 WaPo/NPR/Guardian/WSJ/NYT/CBC/LeMonde 等）。

## 5. 结论

**主力引擎 = httpx（抓取）+ trafilatura（正文）+ Scrapling 解析层（自适应/兜底）**，全部实测通过且内存极低；Crawl4AI 与 Scrapling 浏览器层在本机被上游平台排除（证据完整）；JS 站点走站点规则/外部渲染（见 DECISIONS）。
