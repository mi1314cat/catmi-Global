# OPTIMIZATION_REPORT (R11, 2026-09-11)

## Authentication (全部实测)
| 项 | 结果 |
|---|---|
| Web 未登录访问 / | PASS (302→/login.html) |
| Web 登录 | PASS (scrypt 复用, HttpOnly+Secure+SameSite=Lax cookie) |
| Logout | PASS (session 失效, / 回 302) |
| Admin | PASS (/api/admin/* session+CSRF 不变) |
| MCP | PASS (Bearer 独立, 12 工具 200 全程回归) |
| /api/search 未授权 | PASS→401; 开关开→200; 关→401 (后台可切换, 持久化 feature-flags.json) |

## API
公开保留: /api/health /api/news /api/news/latest /api/news/:id /api/stories /api/trending /api/sources /api/media (200 实测)。/api/search 已保护(默认需 Bearer/session, admin 开关可放行)。public_rest=false 总闸可用。

## Economic Search (矩阵实测: 改善前→后)
MLF 0→0(月度窗口, 靠 gnews-cn-rates 积累+扩展搜索补) | 逆回购 3→8 | 日本央行 2→7 | LPR 79 | CPI 32 | ECB 31 | interest rate 46 | 原油 44 | 黄金 21。新增 7 源全出文: fed 21/ecb 18/cnbc 28/mw 72/inv 10/cn-business 34/cn-rates 38。单轮 scan new 44→124。
查询扩展实测: "美联储降息"→2 个英文扩展(FOMC/rate cut), web 结果 20 条其中 **10 条来自英文扩展**, 中英混合。

## 遗留 (下轮)
- 后台设置页三开关可视化按钮(当前 API 级已可用: POST /api/admin/flags {toggle:...})
- 19 查询 24h 复测(等新源积累)
- gnews-cn 源随时间补量; MLF 等月度窗口词靠扩展搜索兜底

## 回滚
flags.json 删除=默认; ui_gate 关=公开 UI; git revert 每阶段独立提交。
