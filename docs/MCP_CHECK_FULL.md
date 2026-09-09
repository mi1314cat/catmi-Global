# MCP Streamable HTTP 只读服务器研究报告（2026-09-09）

> 调研日期：2026-09-09。目标环境：FreeBSD 共享主机，Node.js 22.22.2 / Python 3.11.13，无 root、无 Docker、512MB 内存，只读 news 搜索工具，Streamable HTTP 传输。
> 本报告所有规范事实均来自 modelcontextprotocol.io 官方规范页、官方 SDK 仓库/源码/npm/PyPI 元数据，逐条标注来源。无任何真实 token/密钥。

---

## 1. 最新规范版本

**结论：当前最新版是 2026-07-28（2026-07-28 正式发布），不是 2025-11-25。** 在 2025-06-18 之后共发布了两个版本：

| 版本 | 状态 | 发布/定稿 | 关键变化 |
|---|---|---|---|
| 2024-11-05 | 已淘汰 | — | 旧 HTTP+SSE 传输 |
| 2025-03-26 | 稳定（旧） | — | 引入 Streamable HTTP；**允许 JSON-RPC batch**；引入 Mcp-Session-Id |
| 2025-06-18 | 稳定（旧） | — | **移除 batch**；引入 `MCP-Protocol-Version` 头；OAuth 加固（RFC 8707 强制） |
| 2025-11-25 | 稳定（前一版） | 2025-11-25 | SSE 可轮询（服务器可主动断开+`retry`）、priming event、无效 Origin 必须 403、OAuth 加 CIMD/增量 scope |
| **2026-07-28** | **最新稳定** | 2026-07-28 | **无状态化**：移除 initialize 握手、`Mcp-Session-Id`、GET 流、`ping`、Last-Event-ID；新增 `server/discover`、每请求 `_meta` 信封、`Mcp-Method`/`Mcp-Name` 头、MRTR、`subscriptions/listen` |

- 官方发布博客：[The 2026-07-28 Specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/)（明确写 "officially pushing the release button"）。
- 规范首页（最新版跳转）：https://modelcontextprotocol.io/specification/2026-07-28
  - 2026-07-28 关键页面：
    - Streamable HTTP 传输：https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
    - 版本协商/兼容：https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
    - 2025-11-25 传输（旧但绝大多数客户端仍在用）：https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
  - 下一版草案已在 `/specification/draft/` 路径下开发（[文档索引](https://modelcontextprotocol.io/llms.txt)），版本路径规律：`/specification/<YYYY-MM-DD>/...`。
- 官方 changelog：
  - 2025-11-25：https://modelcontextprotocol.io/specification/2025-11-25/changelog
  - 2026-07-28：https://modelcontextprotocol.io/specification/2026-07-28/changelog

**对你部署的影响（一句话）**：2026-07-28 于 2026-07-28 才发布（写作时仅 6 周），绝大多数现役客户端仍按 2025 系（initialize 握手）连接；但新规范完全向后兼容思路是"服务器同时伺服两个时代"。下文第 2 节按"旧时代（2025-03-26~2025-11-25）"与"新时代（2026-07-28）"分别给出精确行为，第 7 节给出落地建议。

---

## 2. Streamable HTTP 传输的精确协议细节

### 2.1 Endpoint 约定

- 服务器**必须**提供**单一 HTTP 端点路径**（"MCP endpoint"），同时/分别处理 POST（旧规范还要求支持 GET）。规范举例 `https://example.com/mcp`，**路径可自定义**——规范只要求"一个端点"，`/mcp` 只是惯例：
  - 2025-06-18/2025-11-25: "The server MUST provide a single HTTP endpoint path ... For example, this could be a URL like `https://example.com/mcp`"（[2025-11-25 Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http)）
  - 2026-07-28: "The server MUST provide a single HTTP endpoint path ... that supports POST"（[2026-07-28 Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#security--endpoint)）
- 官方 SDK 默认路径都是 `/mcp`（Python v2 `run()` 的 `streamable_http_path=` 默认 `/mcp`，[py.sdk.modelcontextprotocol.io/run](https://py.sdk.modelcontextprotocol.io/run/)）。放在反代后面挂到任意前缀都合规。

### 2.2 POST 请求

客户端侧要求（三个时代一致的部分）：
- 每条 JSON-RPC 消息 = 一个新 HTTP POST 到 MCP endpoint。
- **Accept 头必须同时列出 `application/json` 和 `text/event-stream`**（GET 请求只要求 `text/event-stream`）。
- `Content-Type: application/json`。
- body 为**单条** JSON-RPC request/notification/response（UTF-8）。

**Batch 的版本分歧（重要）**：
- 2025-03-26：允许 JSON-RPC batch（数组）。
- **2025-06-18 起移除 batch**：body 必须是单条消息。官方 changelog 原文："Remove support for JSON-RPC **batching** (PR [#416](https://github.com/modelcontextprotocol/specification/pull/416))"（[2025-06-18 changelog](https://modelcontextprotocol.io/specification/2025-06-18/changelog#major-changes)；另见 [2025-06-18 Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#sending-messages-to-the-server) 的 "MUST be a single JSON-RPC request, notification, or response"）。
- 2026-07-28：body 只能是单条 request 或 notification，且**客户端不得再发送 JSON-RPC response**（"The client MUST NOT send JSON-RPC responses"，[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#sending-messages)）。
- SDK 行为注记：TS SDK v1.30.0 源码仍会解析数组（`if (Array.isArray(rawMessage))`），即对 batch 宽容；v2 则显式限制 batch ≤100 条并返回 `400/-32600`（[changeset request-body-size-limit](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/.changeset/request-body-size-limit.md)）。自写服务器按规范直接拒绝数组即可（`400` + `-32600`）。

新时代（2026-07-28）POST 额外要求（每个 POST）：
- 必须带 `MCP-Protocol-Version: 2026-07-28`，且与 body `_meta["io.modelcontextprotocol/protocolVersion"]` **一致**，否则 `400` + JSON-RPC `-32020`（HeaderMismatch）。
- 必须带 `Mcp-Method: <method>`；对 `tools/call`、`resources/read`、`prompts/get` 还必须带 `Mcp-Name: <params.name|params.uri>`；服务器必须校验头与 body 一致（`-32020`）。值含非 ASCII/控制字符时用哨兵格式 `=?base64?<b64>?=`。
- 工具参数可标注 `x-mcp-header`，客户端必须镜像成 `Mcp-Param-{Name}` 头（可选特性，但客户端必须支持）。
  - 全部细节：https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#request-metadata
- 精确示例（来自规范）：

```http
POST /mcp HTTP/1.1
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: get_weather

{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_weather","arguments":{"location":"Seattle, WA"},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"ExampleClient","version":"1.0.0"},"io.modelcontextprotocol/clientCapabilities":{}}}}
```

旧时代 POST 的头：
- 初始化后的所有请求：`MCP-Protocol-Version: <协商版本>`（**自 2025-06-18 起要求**；缺失时服务器应按 `2025-03-26` 处理；非法/不支持 → `400`）。
- 有会话时：`Mcp-Session-Id: <id>`。
- 完整精确字段：`jsonrpc: "2.0"`, `id`(string|number, 不可 null, 不可与未决请求重复), `method`, `params`。

### 2.3 响应模式：application/json vs text/event-stream

**规则**（对 request 的 POST）：
- 服务器**必须**二选一返回：`Content-Type: application/json`（单个 JSON 对象）或 `Content-Type: text/event-stream`（SSE 流）。客户端必须两种都支持。（三个时代相同表述，见 [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#sending-messages-to-the-server) / [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#sending-messages)）
- **服务器自主选择**。规范没有强制条件，实践规则：
  - TS SDK v1：默认 SSE；`enableJsonResponse: true` 时全部回 JSON（[webStandardStreamableHttp.ts 源码](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/webStandardStreamableHttp.ts)，`this._enableJsonResponse = options.enableJsonResponse ?? false`，注释 "The default behavior is to use SSE streaming"）。
  - Python v2：`json_response=True` 逐请求回 JSON，默认 SSE（[run 文档](https://py.sdk.modelcontextprotocol.io/run/)）。
  - 服务器需要在响应中**先发通知/进度再发最终 response** 时只能选 SSE；纯单响应服务器回 JSON 完全合规且最省资源。
- 对**只读搜索工具**：推荐 `application/json` 短响应（无长连接、无反代缓冲问题、内存友好）。规范完全允许。
- 若是 notification 或（2025 时代的）response 的 POST：服务器接受则**必须**返回 `202 Accepted`，无 body（三个时代一致）；拒绝则返回 4xx（可带无 `id` 的 JSON-RPC error）。

### 2.4 GET /mcp

- **2025-03-26 ~ 2025-11-25**：客户端可对 endpoint 发 GET 打开"standalone SSE 流"接收服务器主动消息。客户端必须带 `Accept: text/event-stream`。服务器**要么**返回 `text/event-stream`，**要么返回 `405 Method Not Allowed`**（表示不提供该流）——**405 明确允许**（[2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#listening-for-messages-from-the-server)）。在该流上禁止发送 JSON-RPC response（除非是重放）。
  - TS SDK 细节：GET 缺 Accept 时回 `406`；同一 session 已有 GET 流时再开 → `409`（SDK 源码 `handleGetRequest`）。
- **2026-07-28**：GET 流**整个被移除**（changelog "Removal of the GET stream endpoint"）。只支持该版的服务器对 GET 应回 `405`（规范明确列出旧客户端发 GET/DELETE 时的兼容响应：`405 Method Not Allowed`，[2026-07-28 §Backward Compatibility/Earlier revisions](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#earlier-streamable-http-revisions)）。
- 服务器主动推送改为 `subscriptions/listen`：一个**POST** 请求，其响应本身就是长开 SSE 流（[subscriptions 模式](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions)）。只读 news 服务器不需要实现它。

### 2.5 DELETE /mcp（旧时代会话终止）

- 客户端不再需要会话时**应当**对 endpoint 发 `DELETE` + `Mcp-Session-Id` 头显式终止（2025-06-18 与 2025-11-25 相同）。
- 服务器**可以**回 `405 Method Not Allowed` 表示不允许客户端终止会话（合规）；TS SDK 实际实现为校验会话后回 `200` 并关闭会话（[SDK 源码 handleDeleteRequest](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/webStandardStreamableHttp.ts)）。
- 2026-07-28：DELETE 无语义；服务器应回 `405`。

### 2.6 会话管理（Mcp-Session-Id）

- 分配：服务器**可以**（MAY）在初始化时（包含 `InitializeResult` 的 HTTP 响应上）用 `Mcp-Session-Id` 头下发会话 ID。
  - ID **应当**全局唯一且密码学安全（安全随机 UUID、JWT 或加密哈希）；**只能含可见 ASCII（0x21–0x7E）**。（[2025-11-25 Session Management](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#session-management)）
- 客户端义务：初始化响应若带 `Mcp-Session-Id`，之后**所有** HTTP 请求必须带上。
- 服务器义务：
  - 要求会话的服务器对缺头的非初始化请求**应**回 `400 Bad Request`；
  - 会话过期/终止后对该会话 ID **必须**回 `404 Not Found`，客户端收到 404 后必须重新发 `initialize`（不带会话 ID）。
- **无状态服务器可以不下发 session id 吗？——可以。** 规范原文是 MAY（可选），不下发即无会话义务；TS SDK 官方无状态模式 `sessionIdGenerator: undefined`："No Session ID is included in any responses; No session validation is performed"（[源码注释](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/streamableHttp.ts)）。2026-07-28 更是彻底移除会话概念（changelog：[SEP-2567/2575](https://modelcontextprotocol.io/specification/2026-07-28/changelog)）。
- 会话安全要求：不得用会话做认证；会话 ID 要安全随机；应绑定到已认证用户（`<user_id>:<session_id>` 键格式）等——见 [Security Best Practices §Session Hijacking](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices#session-hijacking)。

### 2.7 协议版本协商

**旧时代（2025-06-18 / 2025-11-25，initialize 握手）**：
- 客户端发 `initialize` 请求，`params.protocolVersion` 为其支持的最新版本；服务器若支持**必须原样返回**该版本，否则返回自己支持的**最新**版本；客户端不支持服务器响应的版本则应断开。
- `initialize` 成功后客户端**必须**发 `notifications/initialized` 通知。
- 之后所有 HTTP 请求**必须**带 `MCP-Protocol-Version: <协商版本>` 头。缺失时服务器**应**假定 `2025-03-26`；非法/不支持 → **必须** `400`。（[2025-11-25 Lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle#version-negotiation)、[Transports §Protocol Version Header](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#protocol-version-header)）
- **该头从 2025-06-18 版本开始要求**：changelog 原文 "Require negotiated protocol version to be specified via `MCP-Protocol-Version` header in subsequent requests when using HTTP (PR [#548](https://github.com/modelcontextprotocol/specification/pull/548))"（[2025-06-18 changelog](https://modelcontextprotocol.io/specification/2025-06-18/changelog#major-changes)）；2025-03-26 无此头。
- 版本不匹配错误示例（规范原文）：`{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"Unsupported protocol version","data":{"supported":["2024-11-05"],"requested":"1.0.0"}}}`。

**新时代（2026-07-28，无握手）**：
- **无 initialize**。每个请求自带 `_meta`：必填 `io.modelcontextprotocol/protocolVersion`、`io.modelcontextprotocol/clientCapabilities`；应填（SHOULD）`io.modelcontextprotocol/clientInfo`。缺必填字段 → `400` + `-32602`（[2026-07-28 basic §_meta](https://modelcontextprotocol.io/specification/2026-07-28/basic/index#_meta)）。
- 服务器**必须**实现 `server/discover` RPC，返回 `{"resultType":"complete","supportedVersions":[...],"capabilities":{...},"_meta":{"io.modelcontextprotocol/serverInfo":{...}},"instructions":...,"ttlMs":...,"cacheScope":...}`（[2026-07-28 Discover](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)）。
- 服务器不支持请求的版本 → `400` + `-32022`，`data` 中列出 `supported` 列表：
  ```json
  {"jsonrpc":"2.0","id":1,"error":{"code":-32022,"message":"Unsupported protocol version","data":{"supported":["2026-07-28","2025-11-25"],"requested":"1900-01-01"}}}
  ```
- 请求了不认识的 method → `404 Not Found` + `-32601`（新时代）。
- 服务器不支持 2025-06-18 之前客户端时，可以**拒绝**缺 `MCP-Protocol-Version` 头的请求；若要兼容极老客户端则可把缺头请求按 `2025-03-26` 处理（[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#protocol-version-header)）。

### 2.8 Resumability（Last-Event-ID 重放）

- **2025-03-26 / 2025-06-18**：服务器**可以**给 SSE 事件附加 `id`；断线后客户端用 `GET + Last-Event-ID` 头恢复，服务器**不得**重放其它流上的消息（[2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#resumability-and-redelivery)）。
- **2025-11-25 增强（SEP-1699）**：
  - 服务器**应当**在 SSE 流开头发送一个**priming event**：有 `id`、`data` 为空，让客户端先拿到恢复游标；
  - 服务器可以随时断开连接（不终止流）实现"客户端轮询"——断开前**应**发一个含标准 `retry:` 字段的 SSE 事件，客户端必须尊重该毫秒数；
  - 恢复**永远**通过 `GET + Last-Event-ID`（无论原流是 POST 还是 GET 打开的）；事件 ID **应当**编码流身份，且会话内全局唯一。
  - （[2025-11-25 Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#resumability-and-redelivery)、[changelog SEP-1699](https://modelcontextprotocol.io/specification/2025-11-25/changelog)）
- **2026-07-28：整个移除**："Removal of SSE stream resumability and message redelivery (the Last-Event-ID header and SSE event IDs)"；流断了 = 该请求作废，客户端**必须**用新请求 ID 重发（[2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)）。
- **简单只读服务器能否省略？能。** 重放机制在 2025 系就是可选的（MAY，且 TS SDK 需要 `eventStore` 选项显式开启，未配置时 priming event 也不发——SDK 源码 `if (!this._eventStore) return`）。客户端从不强制要求。省略后唯一后果：长请求中途断线需客户端整体重试。

### 2.9 SSE 响应的精确格式

来自规范 + TS SDK 源码（`writeSSEEvent`）：
- 每条 JSON-RPC 消息一个事件：**`event: message`** + **`data: <单行紧凑 JSON>`** + 空行，即：

```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}

```

- 若启用重放，在 `data:` 行前加 `id: <eventId>` 行（会话内全局唯一）。
- **保活**：SSE 注释行 `:`（如 `:\r\n`），客户端必须忽略；TS SDK v1.30.0 默认每 **15000 ms** 发一次注释帧（`DEFAULT_SSE_KEEP_ALIVE_MS = 15_000`，[sseKeepAlive.ts](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/sseKeepAlive.ts)；1.30.0 release note "send SSE keep-alive comment frames"）。
- 服务器主动断开前发 `retry: <毫秒>` 事件（2025-11-25+）。
- 响应头（TS SDK 实际发送）：`Content-Type: text/event-stream`、`Cache-Control: no-cache, no-transform`、`Connection: keep-alive`、`X-Accel-Buffering: no`（反代不缓冲；`X-Accel-Buffering` 在 2026-07-28 规范中已成 SHOULD）。
- HTTP 响应头里（若有会话）带 `mcp-session-id: <id>`。

### 2.10 HTTP 状态码约定（汇总表）

| 状态码 | 语义 | 出处 |
|---|---|---|
| `200` + JSON/SSE | 对 request 的正常应答（JSON-RPC **协议错误也在 200 的 body 里**，不是 4xx） | 全部版本 |
| `202 Accepted` | POST 的 body 只是 notification 或（2025 系的）response 时，接受即 202、无 body | [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#sending-messages-to-the-server) |
| `400 Bad Request` | 解析错误 `-32700`；需要会话但缺 `Mcp-Session-Id`；`MCP-Protocol-Version` 非法；2026：缺 `_meta` 必填字段 `-32602`、头不一致 `-32020`、缺能力 `-32021`、版本不支持 `-32022`、batch 超限 `-32600` | 各节 |
| `403 Forbidden` | `Origin` 头存在且非法（body MAY 为无 id 的 JSON-RPC error） | [2025-11-25 changelog PR#1439](https://modelcontextprotocol.io/specification/2025-11-25/changelog) |
| `404 Not Found` | 会话 ID 失效/未知（旧）；2026：method 未知 + `-32601` | 同上 |
| `405 Method Not Allowed` | GET 不提供 SSE 流；DELETE 不允许终止会话；其它方法（PUT/PATCH 等，SDK 附 `Allow: GET, POST, DELETE`） | 2.4/2.5 节 |
| `406 Not Acceptable` | （SDK 行为）Accept 头缺要求的媒体类型 | [SDK 源码](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/webStandardStreamableHttp.ts) |
| `413 Payload Too Large` | （SDK 行为）body 超 4 MiB 默认上限 | [v2 changeset](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/.changeset/request-body-size-limit.md) |
| `415 Unsupported Media Type` | （SDK 行为）Content-Type 不是 application/json | 同上 |

JSON-RPC → HTTP 错误映射关键点：**协议级 JSON-RPC error（如 unknown tool `-32602`、内部错误 `-32603`）装在 HTTP 200 的 JSON body（或 SSE 事件）里返回**；HTTP 4xx/5xx 只用于传输/会话/校验层失败。

---

## 3. 认证

### 3.1 规范要求

- 认证**可选**（"Authorization is OPTIONAL for MCP implementations"）。HTTP 传输若实现，**应当**遵循 MCP 的 OAuth 配置；stdio 传输不应使用该机制而从环境取凭证；"clients and servers MAY negotiate their own custom authentication and authorization strategies"（[2025-11-25 Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#protocol-requirements)、[2026-07-28 basic §Auth](https://modelcontextprotocol.io/specification/2026-07-28/basic/index#auth)）。
- OAuth 2.1 从 2025-03-26 版本起就是 MCP HTTP 传输的推荐机制（2025-06-18 加入 RFC 8707 资源指示符强制要求；2025-11-25 加 CIMD 与增量 scope；2026-07-28 加 RFC 9207 `iss` 校验、DCR 弃用）。
- 基于 HTTP 的服务器被视作 **OAuth 2.1 Resource Server**：
  - 令牌**必须**放在 `Authorization: Bearer <token>` 头（**每个**请求都要带，包括同一逻辑会话的每个请求）；**不得**放 query string。
  - 服务器**必须**验证令牌 audience（RFC 8707）：令牌必须是签给本 MCP 服务器的；token passthrough **被明确禁止**。
  - 401 响应必须可被客户端解析：
    ```http
    HTTP/1.1 401 Unauthorized
    WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource", scope="files:read"
    ```
    （`resource_metadata` 指向 RFC 9728 Protected Resource Metadata；也可以只提供 well-known URI 兜底。）
  - 运行中 scope 不足 → `403` + `WWW-Authenticate: Bearer error="insufficient_scope", scope="...", resource_metadata="..."`。
  - 错误码表：401=缺失/无效令牌；403=scope 不足；400=请求畸形。（[2025-11-25 Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#protected-resource-metadata-discovery-requirements)）
- 客户端义务（OAuth 流）：必须实现 RFC 8707 `resource` 参数、PKCE S256、按优先级发现 AS metadata（RFC 8414 路径插入 → OIDC）等。
- 2026-07-28 的变化：AS **应当**在授权响应中返回 `iss`（RFC 9207），客户端**必须**校验；**DCR（RFC 7591）被正式弃用**，转向 Client ID Metadata Documents (CIMD)；凭证绑定 issuer。（[2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated)、[官方博客 §Authorization](https://blog.modelcontextprotocol.io/posts/2026-07-28/#authorization)）

### 3.2 静态 Bearer Token：规范允许吗？常见吗？

- **规范层面**：OAuth 之外的自定义认证被明确允许（"MAY negotiate their own custom authentication and authorization strategies"）。规范**没有**定义"静态 token"模式，但也**不禁止**——大量生产 MCP 服务器（Linear、Sentry、GitHub、Supabase 等公开 MCP）用静态 bearer/个人访问令牌 + 自定义 header 方式。这属于"自定义认证"且与 OAuth 的 `Authorization: Bearer` 头格式天然兼容。
- **客户端层面**：主流客户端普遍支持为远程 HTTP MCP 配置静态 header（见第 6 节）。
- **实务建议（公网只读 news 服务器）**：
  - 要求 `Authorization: Bearer <静态随机长 token>`（≥32 字节随机），常量时间比较（如 Node `crypto.timingSafeEqual`）；
  - 失败统一回 `401` + `WWW-Authenticate: Bearer resource_metadata="..."`（即使不做完整 OAuth，也回这个头，客户端的发现逻辑不会因此崩）；
  - **token 不写日志**；用环境变量存储；支持轮换（同时接受新旧两个值）。
- 若用户需要多用户/浏览器内认证，再考虑完整 OAuth 2.1（或托管在 Cloudflare Access / 平台认证之后）。

---

## 4. Origin 校验（DNS 重绑定防护）

- 规范要求（三个时代均为 MUST）："Servers MUST validate the `Origin` header on all incoming connections to prevent DNS rebinding attacks"；**2025-11-25 起明确**："If the `Origin` header is present and invalid, servers MUST respond with HTTP 403 Forbidden"，body 可以是无 `id` 的 JSON-RPC error（[2025-11-25 Transports §Security Warning](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#security-warning)、[2026-07-28 同节](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#security--endpoint)；2025-11-25 changelog PR #1439 专门澄清 403）。
- **非浏览器客户端（无 Origin 头）怎么办**：规范的 403 条件措辞是 "**present and invalid**"——即 Origin 缺失时不触发 403 条款。官方 TS SDK 的实现正是如此：`if (originHeader && !allowedOrigins.includes(originHeader)) → 403`，无 Origin 直接放行（[SDK 源码 validateOrigin](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/webStandardStreamableHttp.ts)）。因此标准做法是：**Origin 存在且不在白名单 → 403；Origin 不存在 → 放行（配合认证兜底）**。
- **localhost 例外**：规范未定义任何 "localhost Origin 例外"条款。防 DNS rebinding 的配套建议是本机运行时只绑 127.0.0.1（SHOULD bind only to localhost）。浏览器对 localhost 页面发的 Origin 是 `http://localhost:<port>` 等真实值，按白名单处理即可。SDK 还支持校验 `Host` 头（`allowedHosts`）——这是 DNS rebinding 的另一半防护（Origin 只是其一）。
- SDK 弃用注记：TS SDK 的内置 `enableDnsRebindingProtection/allowedOrigins/allowedHosts` 选项已标 `@deprecated`，官方建议放到外层中间件/反代做（"Use external middleware for origin validation instead"——[源码选项注释](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/webStandardStreamableHttp.ts)）。v2 的 `createMcpHandler`/`createMcpHonoApp`/`createMcpExpressApp` 仍在 body 解析**之前**做 Host/Origin 校验（[changeset request-body-size-limit](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/.changeset/request-body-size-limit.md)）。
- 2025-03-26 版本措辞差异：只说 "MUST validate the Origin header"，没有 403 状态码的明确规定（403 是 2025-11-25 的 PR #1439 加进去的）。

---

## 5. 官方 SDK

### 5.1 TypeScript

**两条产品线并存**（2026-07-27/28 拆分）：

**① v1 线（2025 时代协议，维护态）：`@modelcontextprotocol/sdk` 1.30.0**（npm dist-tag `latest`，2026-07-27 发布；node >=18）
- 纯 JS，**无任何原生二进制依赖（node-gyp 不需要）**。依赖全部为 JS 包：`ajv, zod, cors, hono, jose, express@5, raw-body, ajv-formats, cross-spawn, eventsource, content-type, pkce-challenge, @hono/node-server, json-schema-typed, eventsource-parser, express-rate-limit, zod-to-json-schema`（npm registry manifest，2026-09-09 抓取）。
- 支持协议版本常量（源码 `src/types.ts`）：`LATEST_PROTOCOL_VERSION = '2025-11-25'`；`SUPPORTED_PROTOCOL_VERSIONS = ['2025-11-25','2025-06-18','2025-03-26','2024-11-05','2024-10-07']`；`DEFAULT_NEGOTIATED_PROTOCOL_VERSION = '2025-03-26'`。
- **`StreamableHTTPServerTransport` 精确 API**（[streamableHttp.ts](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/src/server/streamableHttp.ts)，207 行，是 `WebStandardStreamableHTTPServerTransport` 的 Node 适配壳，内部用 `@hono/node-server` 的 `getRequestListener` 转换 Node ↔ Web 标准流）：

  ```ts
  class StreamableHTTPServerTransport implements Transport {
    constructor(options: StreamableHTTPServerTransportOptions = {})
    get sessionId(): string | undefined
    async start(): Promise<void>            // no-op
    async close(): Promise<void>
    async send(message: JSONRPCMessage, options?: { relatedRequestId?: RequestId }): Promise<void>
    async handleRequest(
      req: IncomingMessage & { auth?: AuthInfo },
      res: ServerResponse,
      parsedBody?: unknown                  // 可传预解析 body（如 express.json() 的结果）
    ): Promise<void>
    closeSSEStream(requestId: RequestId): void        // 用于长操作轮询
    closeStandaloneSSEStream(): void                  // 关闭 GET 流触发客户端重连
  }
  ```

  - `StreamableHTTPServerTransportOptions`（同 `WebStandardStreamableHTTPServerTransportOptions`）：`sessionIdGenerator?: () => string`（**`undefined` = 无状态模式：不下发、不校验 session id**）、`onsessioninitialized?`、`onsessionclosed?`、`enableJsonResponse?: boolean`（默认 `false` → SSE）、`eventStore?: EventStore`（不配则无重放/无 priming event）、`enableDnsRebindingProtection?: boolean`（默认 false）、`allowedHosts?/allowedOrigins?`（已 `@deprecated`）、`keepAliveMs?`（默认 15000）。
  - 无状态模式注意：SDK 要求无状态模式下**每个请求用全新 transport 实例**（源码注释 "In stateless mode (no sessionIdGenerator), each request must use a fresh transport"，否则报错）。
  - 官方示例：`simpleStatelessStreamableHttp.ts`（无状态）、`jsonResponseStreamableHttp.ts`（纯 JSON 模式）等（[v1 README 示例表](https://github.com/modelcontextprotocol/typescript-sdk/blob/1.30.0/README.md)）。

**能否脱离 Express、直接用 `node:http`？——能，且不需要写额外适配层：**

```js
// Node 22, CommonJS/ESM 均可；@modelcontextprotocol/sdk 1.30.0
import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

// 无状态 + 纯 JSON 响应（最省内存的只读形态）
function makeTransport() {
  return new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,   // 无会话
    enableJsonResponse: true,        // application/json 短响应
  });
}
const server = http.createServer(async (req, res) => {
  // 1) 认证（自定义 Bearer）
  // 2) Origin 校验：存在且不在白名单 → 403
  // 3) 仅处理 POST/GET/DELETE 到 /mcp，其余 404
  const transport = makeTransport();               // 无状态：每请求新实例
  const server = new McpServer({ name: 'news', version: '1.0.0' });
  /* 注册 tools ... */
  await server.connect(transport);
  await transport.handleRequest(req, res);         // 直接吃 node:http 对象
});
server.listen(8080, '127.0.0.1');
```

  依据：`handleRequest(req: IncomingMessage, res: ServerResponse, parsedBody?)` 的签名即为此设计；内部 `@hono/node-server` 负责转换与 SSE。Express 只是为了官方示例的 `express.json()` 预解析（此时传第三参 `parsedBody`）。

**② v2 线（2026-07-28 协议）：多包拆分**，全部 2.0.0，2026-07-27/28 发布（[releases](https://github.com/modelcontextprotocol/typescript-sdk/releases)）：
- `@modelcontextprotocol/core@2.0.0`（schema/协议常量）、`@modelcontextprotocol/server@2.0.0`（deps: `zod@^4.2.0` + core；node >=20）、`@modelcontextprotocol/client@2.0.0`、`@modelcontextprotocol/node@2.0.0`（deps: `@hono/node-server`；peer: `hono` + `server`；node >=20）、`@modelcontextprotocol/hono` / `@modelcontextprotocol/express` / `@modelcontextprotocol/fastify`（框架适配器）、`@modelcontextprotocol/server-legacy@2.0.0`。（npm dist-tags，2026-09-09 抓取）
- v2 文档：https://ts.sdk.modelcontextprotocol.io/v2 （"the stable release line implementing the 2026-07-28 spec"）
- **新时代 HTTP 服务入口**（[migration/support-2026-07-28](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28.html)）：

  ```ts
  import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
  import { toNodeHandler } from '@modelcontextprotocol/node';

  const handler = createMcpHandler(() => {
    const server = new McpServer({ name: 'news', version: '1.0.0' }, { capabilities: { tools: {} } });
    server.registerTool('search_news', { inputSchema: z.object({ q: z.string() }) }, async ({ q }) => ({ /* ... */ }));
    return server;
  }); // 默认 legacy:'stateless'：同一入口同时伺服 2026-07-28 与 2025 时代流量

  // Web 标准 runtime: export default handler;
  // Node（原生 node:http / 任意框架）:
  app.all('/mcp', toNodeHandler(handler));
  ```

  - `createMcpHandler` 是 **Web 标准 fetch 形态**（`{ fetch, close, notify, bus }`）；Node 侧用 `toNodeHandler(handler, { onerror? })` 包一次即可接 `node:http`。
  - v2 默认 4 MiB 请求体上限（413）、batch ≤100、Host/Origin 校验前置；`isLegacyRequest(request)`、`legacyStatelessFallback(factory)` 辅助双时代路由。
  - 请求体大小/校验细节：[changeset request-body-size-limit](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/.changeset/request-body-size-limit.md)、[changeset require-protocol-version-header-on-modern-post](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/.changeset/require-protocol-version-header-on-modern-post.md)。

### 5.2 Python

- **`mcp` 2.2.0**（2026-09-07 发布）为当前版；**2.0.0 于 2026-07-28 与新规范同日发布**；`requires-python >= 3.10`（PyPI JSON，2026-09-09 抓取；版本历史 1.9.4 → 2.0.0 → 2.0.1 → 2.1.0 → 2.1.1 → 2.2.0，72 个 release）。
- **v2 = 2026-07-28 协议**，且同一 `streamable_http_app()` **同时伺服 2025 时代与 2026 时代**客户端（官方 What's new：[py.sdk.modelcontextprotocol.io/whats-new](https://py.sdk.modelcontextprotocol.io/whats-new/)）。
- 高层 API 改名：`FastMCP` → **`MCPServer`**（`from mcp.server import MCPServer`）；类型拆到独立发行版 `mcp-types`（只依赖 pydantic）；字段变 snake_case（`result.is_error`、`tool.input_schema`）；wire 仍是 camelCase。
- 依赖链（`requires_dist`，PyPI）：`anyio>=4.9`、`httpx2>=2.5.0`（v2 起用 httpx2 替代 httpx，TLS 经 truststore 用系统 CA）、`jsonschema>=4.20.0`、`mcp-types==2.2.0`、`opentelemetry-api>=1.28.0`、`pydantic>=2.12.0`、`pyjwt[crypto]>=2.10.1`、`python-multipart`、`sse-starlette>=3.0.0`、`starlette`、`typing-extensions`、`uvicorn`（win32 才有 pywin32）。HTTP 服务栈 = **Starlette + uvicorn**（`run(transport="streamable-http")` 一行起 Starlette app 并用 uvicorn 跑，[run 文档](https://py.sdk.modelcontextprotocol.io/run/)）。
- `run()` 关键参数（全部给到 `run()`，不是构造器）：`host`/`port`（默认 127.0.0.1:8000）、`streamable_http_path`（默认 `/mcp`）、`json_response=True`（纯 JSON 短响应）、`stateless_http=True`（无会话，2025 时代流量也逐请求处理）、`max_request_body_size`（**默认 4 MiB，超出 413**）、`session_idle_timeout`（默认 1800s，legacy 会话）、`max_sessions`（默认 10000）、`event_store`/`retry_interval`/`transport_security`（Host 白名单等 DNS rebinding 防护）。（[run 文档](https://py.sdk.modelcontextprotocol.io/run/)）
- v1 兼容线：`mcp>=1.28,<2`（1.9.4，2025-06-12）为 2025 时代专用，进入维护态（[What's new §Upgrading](https://py.sdk.modelcontextprotocol.io/whats-new/)）。

**FreeBSD 已知问题（重要）**：
- Python v1/v2 都硬依赖 **pydantic（pydantic-core，Rust 扩展）**。pydantic-core **不发布 FreeBSD wheel**（[pydantic-core issue #773](https://github.com/pydantic/pydantic-core/issues/773)：FreeBSD 可自行编译，但 `pip install` 需 Rust + maturin 工具链）。共享主机（无 root、512MB）大概率装不动或很慢。**可行替代**：用 FreeBSD 官方包 `pkg install py311-pydantic-core py311-mcp`（若有 port）或创建 venv 时 `--system-site-packages` 借用系统包。
- **TS SDK 无此问题**（纯 JS，无 node-gyp），Node 22 在 FreeBSD 上跑 `npm install @modelcontextprotocol/sdk` 即可——**在 FreeBSD 共享主机上 TypeScript 是更稳的选择**。
- 其它 Tier 1 SDK：Go（go-sdk）、C#（csharp-sdk）也支持 2026-07-28；Rust SDK beta（[官方博客 §SDKs](https://blog.modelcontextprotocol.io/posts/2026-07-28/#sdks)）。

---

## 6. 客户端支持现状（远程 Streamable HTTP）

> 以下配置形状与行为均核对自各客户端官方文档/发布说明/源码（引用见各条目）。调研日期 2026-09-09。

### 6.1 配置形状（精确 JSON）

| 客户端 | 配置（远程 HTTP） | 自定义 header |
|---|---|---|
| Claude Code | `claude mcp add --transport http <name> <url> --header "Authorization: Bearer <token>"`；JSON：`{"type":"http","url":"https://.../mcp","headers":{...}}`（`streamable-http` 为别名；只有 `url` 不写 `type` 会报错） | ✅ 静态 `--header`/`headers`（含动态 `headersHelper`）；另有 `/mcp` OAuth | 
| Claude Web/Desktop（自定义连接器） | UI 粘贴远程 URL（Customize → Connectors → Add custom connector） | ❌ **无自定义 header**——只有 URL + OAuth Client ID/Secret（[#427](https://github.com/anthropics/claude-ai-mcp/issues/427) 2026-06 被 "closed as not planned"） |
| Claude API（Messages API MCP connector） | `mcp_servers:[{"type":"url","url":"...","name":"...","authorization_token":"<token>"}]` + `tools:[{"type":"mcp_toolset","mcp_server_name":"..."}]`，beta 头 `mcp-client-2025-11-20` | ✅ 静态 `authorization_token`（Bearer）；无任意 header、无内建 OAuth 流（[MCP connector docs](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)） |
| Cursor | `{"mcpServers":{"name":{"url":"https://.../mcp","headers":{"Authorization":"Bearer ${env:TOKEN}"}}}}`（[docs](https://cursor.com/docs/mcp)） | ✅（支持 `${env:...}` 插值；OAuth 服务器存在时**会忽略 headers 强制走 OAuth**——[论坛 156054](https://forum.cursor.com/t/mcp-headers-config-ignored-when-server-has-oauth-discovery/156054)；另有 `tools/call` 丢 header 的报告 [169015](https://forum.cursor.com/t/streamable-http-mcp-mcp-json-headers-besides-x-domainhost-key-are-dropped-on-tools-call/169015)） |
| Cline | `{"mcpServers":{"name":{"type":"streamableHttp","url":"...","headers":{"Authorization":"Bearer <token>"}}}}` —— **不写 `type` 默认按旧 SSE 连**（常见踩坑，[#6767](https://github.com/cline/cline/issues/6767)） | ✅ 静态 headers；OAuth 支持（v4.1.7 起支持预注册客户端，此前仅 DCR）（[CHANGELOG](https://github.com/cline/cline/blob/main/CHANGELOG.md)） |
| VS Code / Copilot agent mode | `{"servers":{"name":{"type":"http","url":"...","headers":{"Authorization":"Bearer ${input:api-token}"}},"inputs":[...]}}`（[config reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)）；先试 Streamable HTTP 失败再回退 SSE | ✅（OAuth 全流自 1.101，2025-06；已知问题：workspace `.mcp.json` headers 被静默丢弃 [vscode#319528](https://github.com/microsoft/vscode/issues/319528)） |
| Gemini CLI | `{"mcpServers":{"name":{"httpUrl":"https://.../mcp","headers":{...}}}}`（`url`=SSE，`httpUrl`=Streamable HTTP） | ✅ 静态 headers + OAuth 自动发现（[docs](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html)） |
| Antigravity | `{"mcpServers":{"name":{"serverUrl":"https://.../mcp/","headers":{...}}}}` | ✅ + OAuth（DCR 或手填 clientId/Secret）（[docs](https://antigravity.google/docs/mcp/)） |
| OpenAI Agents SDK (Python) | `MCPServerStreamableHttp(params={"url":"https://...","headers":{"Authorization":"Bearer <token>"},"timeout":10}, cache_tools_list=True)`（[docs](https://openai.github.io/openai-agents-python/mcp/)） | ✅ headers；**无 OAuth 客户端**（token 自备/`params["auth"]`） |
| OpenAI Responses API（托管 MCP 工具） | `{"type":"mcp","server_label":"...","server_url":"https://...","allowed_tools":[...],"require_approval":"never"}`（[cookbook](https://developers.openai.com/cookbook/examples/mcp/mcp_tool_guide)） | ✅ 但**每次 API 调用都要重传 headers 与 URL**（值不持久化）；服务器必须公网可达；无 OAuth 舞步 |
| Windsurf/Devin Cascade | `{"mcpServers":{"name":{"serverUrl":"...","headers":{...}}}}`（支持 `${env:}`/`${file:}` 插值） | ✅ + 各传输均支持 OAuth（[docs](https://docs.devin.ai/desktop/cascade/mcp)） |
| Goose | Remote Extension (Streamable HTTP)，`goose configure` | ✅ Bearer/headers（header 支持在 [#2423](https://github.com/aaif-goose/goose/issues/2423) 后加入） |
| LibreChat | `{"mcpServers":{"name":{"type":"streamable-http","url":"...","headers":{...}}}}` | ✅ + OAuth 流（[docs](https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/mcp_servers)） |

### 6.2 认证方式分野（一句话结论）

- **只会发静态 `Authorization: Bearer`/自定义 headers（无 MCP OAuth 舞步）**：OpenAI Agents SDK、OpenAI Responses API 托管工具、Claude API connector、Goose、LibreChat(headers 模式)、Cherry Studio。
- **完整 MCP OAuth 2.1（RFC 9728 发现 → DCR/CIMD → PKCE）**：claude.ai/Desktop 自定义连接器（OAuth-only UI）、Claude Code（`/mcp`）、Cursor（含 static OAuth `auth:{clientId,clientSecret}`）、VS Code（1.101+）、Gemini CLI（401 触发自动发现）、Antigravity、Cline（v3.x DCR；v4.1.7+ 预注册）、Windsurf/Devin。
- 对静态 token 服务器的**实务含义**：官方 OAuth-only 的 Claude Web/Desktop 连接器**无法**接你的静态 token 服务器（除非加 OAuth）；Claude Code / Cursor / Cline / VS Code / Gemini CLI / OpenAI 两家都可以。若目标是 Claude Web，可在前面加一层托管 OAuth（或用 Smithery/Composio 这类代理网关）。

### 6.3 发送哪些头？无会话服务器兼容性？

- 所有列出客户端都发送：`Accept: application/json, text/event-stream`、`Content-Type: application/json`、协商后的 `MCP-Protocol-Version`（SDK 生成）、配置的 `Authorization`。
- **`Mcp-Session-Id`**：服务器不下发会话 ID 时客户端不会发送（该字段自 2025-03-26 起就是可选，2026-07-28 整体移除）——**所有被调研客户端都能连无会话服务器**，无已知阻断。
- 实际痛点不是会话，而是：Cursor 的 headers-vs-OAuth 冲突与 header 丢失、VS Code workspace `.mcp.json` headers bug、Cline 的 SSE 默认坑、OpenAI 托管工具的 headers 不持久。

### 6.4 协议版本协商现状（2026-07-28 采纳度，截至 2026-09-09）

**已验证支持 2026-07-28（无状态，无 initialize）**：
- **Claude Code v2.1.232+**：新 "v2 runtime" 基于 TS SDK 2.0，对 HTTP/connector 服务器**主动协商 2026-07-28**（stdio 需 `MCP_PROTOCOL_NEGOTIATION=auto`）；v1 runtime 为 TS SDK 1.x（2025-06-18 时代）（[Claude Code MCP docs](https://code.claude.com/docs/en/mcp)）。
- **OpenAI Agents SDK**：依赖 `mcp>=1.19,<3`——装了 **Python SDK v2** 即以最新版发 `server/discover` 探测、失败回退 legacy initialize；装 v1 则纯 2025 时代（[docs](https://openai.github.io/openai-agents-python/mcp/)）。
- **MCP Inspector**：以 "protocol era" 处理（[protocol-eras 文档](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/protocol-eras)）。

**未发现 2026-07-28 支持证据**（截至调研日，基于官方文档/changelog/issue 检索，属"无证据"而非"确认不支持"）：
- **Cursor**（支持 elicitation → 至少 2025-06-18 时代）；**Cline**（TS SDK 1.x）；**VS Code**（OAuth 跟随 2025-06-18 auth spec）；**Gemini CLI**（源码钉死 `@modelcontextprotocol/sdk` **1.23.0**——[packages/core/package.json](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/package.json)，2026-09-08 nightly）；**Claude Web/Desktop/API**（版本未公开）。

**结论（与第 7 节呼应）**：你的服务器**必须**以 2025 系（initialize 握手）为主协议伺服以上绝大多数客户端；2026-07-28 分支作为前瞻（Claude Code 新 runtime / OpenAI Agents SDK / 未来版本会先用它）。这也与 Python v2 / TS v2 "一个端点同时伺服两个时代" 的设计完全一致。

---

## 7. 最小只读服务器实现清单

### 7.1 旧时代（2025-06-18 / 2025-11-25）——今天绝大多数客户端

**必须实现的方法（4 个）+ 2 个通知处理**：

| 方法 | 响应（精确 JSON） | 来源 |
|---|---|---|
| `initialize` | `{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"news-search","title":"News Search","version":"1.0.0"}}}` — `protocolVersion` 必须回显客户端请求版本（若支持）否则回服务器支持的最新版；[Lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle#initialization) |
| `notifications/initialized` | 通知 → HTTP `202`，无 body | [Lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle#initialization) |
| `ping` | `{"jsonrpc":"2.0","id":3,"result":{}}`（**空 result，立即回复**） | [Ping](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping) |
| `tools/list` | `{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"search_news","title":"Search News","description":"...","inputSchema":{"type":"object","properties":{"query":{"type":"string","description":"..."},"limit":{"type":"integer","minimum":1,"maximum":50}},"required":["query"]}}]}}`（小工具集可不返回 `nextCursor`） | [Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#listing-tools) |
| `tools/call` | 成功：`{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"..."}],"isError":false}}`；业务失败（模型可自纠）：`{"result":{"content":[{"type":"text","text":"Invalid query: ..."}],"isError":true}}`；未知工具/请求畸形：JSON-RPC 协议错误 `{"error":{"code":-32602,"message":"Unknown tool: x"}}` | [Tools §Calling/Error Handling](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#calling-tools) |
| `notifications/cancelled` | 通知 → `202`（可忽略内容） | [Cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation) |
| `notifications/roots/list_changed` 等客户端通知 | 一律 `202` | — |

**可以省略的**：
- `resources/*`、`prompts/*`：不声明对应 capability 即可不实现；实现良好的客户端看到 capabilities 里没有就不会调用；若被调用（客户端不完善），正确应答是 `-32601 Method not found`。
- `logging/setLevel`、`completions`：声明 `logging`/`completions` capability 才需要。
- 会话：完全可省（不下发 `Mcp-Session-Id`）。省略后对缺头请求无需校验。
- SSE：用 `enableJsonResponse` / 纯 JSON 模式，完全不产生流。
- 重放/eventStore：可省（见 2.8）。

**capabilities 声明（initialize 响应里）**：最小为 `"capabilities":{"tools":{}}`；`listChanged:true` 仅当你会推送 `notifications/tools/list_changed` 时才声明（静态只读 news 工具集 → 不声明或 false）。tools capability 声明后**必须**响应 `tools/list`，工具集**可以**为空（[Tools §Capabilities](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#capabilities)）。

**tools/list 分页 cursor 规则**（[Pagination](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/pagination)）：
- 游标是**不透明字符串**；客户端不得解析/修改/跨会话持久化；页大小由服务器定，客户端不得假定。
- 请求：`params.cursor` 可选；响应：`result.nextCursor` 存在 = 还有下一页；缺失 = 结束（客户端 MUST 把缺 `nextCursor` 视为末页）。
- 非法游标 **应** 返回 `-32602`（Invalid params）。
- 只读 news 服务器工具数少 → 直接返回全部工具、不设 `nextCursor`，并忽略请求里的 `cursor`（合规，"Support both paginated and non-paginated flows"）。

**tools/call 响应格式细节**：
- `content` 数组元素类型：`{"type":"text","text":...}` / `{"type":"image","data":<b64>,"mimeType":...}` / `{"type":"audio",...}` / `{"type":"resource_link","uri":...,"name":...}` / `{"type":"resource","resource":{...}}`（[Tool Result](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#tool-result)）。
- `structuredContent`（2025-06-18 起）：结构化 JSON；若提供 `outputSchema` 则**必须**符合；**应当**同时在 `content` 里放一份序列化 JSON 文本以兼容旧客户端。
- `isError: true` 的结果仍走 200 + result；只有**协议错误**才用 JSON-RPC error。
- 2025-11-25 起 Tool 定义可带 `title`、`icons`、`annotations`、`execution.taskSupport`；工具名规范：1–128 字符，`[A-Za-z0-9_.-]`（SHOULD）。

### 7.2 新时代（2026-07-28）附加清单

- **不再**实现 `initialize`/`notifications/initialized`/`ping`（`ping` 是被**移除**而非弃用；收到时按未知方法 `-32601`/404 处理）。
- **必须**实现 `server/discover`（响应形状见 2.7；只读工具服务器返回 `capabilities:{"tools":{}}`）。
- 每个请求校验 `_meta` 信封（`io.modelcontextprotocol/protocolVersion` + `clientCapabilities` 必填）与三个标准头（`MCP-Protocol-Version`/`Mcp-Method`/`Mcp-Name`），不一致 → `400` + `-32020`。
- `tools/list` 响应**必须**含 `resultType:"complete"` + `ttlMs` + `cacheScope`（SDK 默认 `ttlMs:0, cacheScope:'private'`，可用 `ServerOptions.cacheHints` 定制；[Tools 响应示例](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#listing-tools)）；**应当**按确定性顺序返回工具（利于客户端缓存与 prompt cache）。
- `tools/call` 响应同样带 `resultType:"complete"`；content/structuredContent/isError 语义与旧版一致。
- 客户端**不发** responses/notifications（唯一的核心通知 `notifications/cancelled` 仅限 stdio）——POST body 只会是 request（或罕见 notification）；通知 → `202`。
- 客户端**关闭 SSE 响应流 = 取消请求**：服务器应尽快停止工作且不得再发该请求的消息（[Cancellation](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#cancellation)）。
- GET/DELETE/带 `Mcp-Session-Id` 的请求/带 `Last-Event-ID` 的请求：按 2.4/2.5/2.6 的兼容行为处理（405 / 405 / 忽略 / 忽略）。

### 7.3 只读约束的落点

- 只读 = 不提供写工具；仍要防滥用：`tools/call` 的 `arguments` 是模型生成的不可信输入——长度/枚举/数值边界校验后才能用于检索（SEP-1303：输入校验错误应作为 `isError:true` 的 Tool Execution Error 返回，便于模型自纠，[2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)）。
- 搜索结果截断（如前 N 条 + total），避免超大响应。

---

## 8. 公网部署安全最佳实践（512MB 共享主机版）

规范与官方文档明确的要求/建议：
- **认证前置**：先认证再碰任何 MCP 逻辑——包括 `initialize`（[Security Best Practices](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices#session-hijacking)："MCP servers that implement authorization MUST verify all inbound requests; MUST NOT use sessions for authentication"）。
- **速率限制**：规范对工具的要求是 "Rate limit tool invocations"（[Tools §Security Considerations](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#security-considerations)）。TS SDK v1 直接内置 `express-rate-limit` 依赖；公网建议：IP+令牌双键令牌桶，`tools/list` 宽（如 60/min）、`tools/call` 严（如 10–20/min），超限回 `429` + `Retry-After`。
- **请求体大小**：v2 SDK/Python v2 默认 **4 MiB**（超出 `413`），batch ≤100 条；自建建议对只读搜索服务器收紧到 128–256 KiB（[v2 changeset](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/.changeset/request-body-size-limit.md)、[Python run 文档](https://py.sdk.modelcontextprotocol.io/run/)）。
- **超时**：请求超时是规范级 SHOULD（"Implementations SHOULD establish timeouts for all sent requests... SHOULD always enforce a maximum timeout"；[Lifecycle §Timeouts](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle#timeouts)）。服务器侧：工具执行硬超时（如 20s）、SSE keep-alive 15s（SDK 默认）、legacy 会话闲置 1800s 上限（Python v2 `session_idle_timeout`）。
- **Origin/Host 校验**：见第 4 节；v2 SDK 在 body 解析前做校验（非法 Origin+畸形 body → 403 且不读 body）。
- **会话（若用）**：ID 用 CSPRNG；**拒绝客户端自造的 session id**（只在 initialize 时签发——防 session 固定）；绑定认证身份（`<user_id>:<session_id>`）；过期必须 404。（[Security Best Practices §Session Hijacking](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices#session-hijacking)）
- **SSE 挂连接耗尽**：每 IP 并发流上限（SDK 已限每会话仅 1 条 GET 流，409）；开 `keep-alive` 注释帧防中间件杀空闲连接；**能选 JSON 响应就不要开 SSE**（`enableJsonResponse`/`json_response=True`）——只读工具服务器无服务器主动消息，SSE 只会白占内存与 fd（512MB 下尤其重要）。
- **日志要点**：记录时间、来源 IP、`Mcp-Method`/`Mcp-Name` 头（新时代专为网关观测设计）、method、request id、状态码、耗时；**脱敏** `Authorization` 与 `params`（query 可能含隐私）；错误响应不回显堆栈（协议错误信息按需，内部错误固定 `-32603 "Internal server error"`）。
- **常见漏洞清单**：
  - 未授权 `initialize`（认证必须覆盖所有路径）；
  - token passthrough / 令牌 audience 不校验（明确禁止；[Authorization §Token Passthrough](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#token-audience-binding-and-validation)）；
  - session 固定/劫持（见上）；
  - DNS rebinding（Origin+Host）；
  - SSRF：若服务器会根据参数取外部 URL（news 抓取），必须出网白名单 + 禁私网/链路本地地址（含 169.254.169.254），禁止跟随重定向到内网（[Security Best Practices §SSRF](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices#server-side-request-forgery-ssrf)）；
  - 超大输出/无限分页导致内存放大；
  - prompt injection 经工具描述/结果回流（工具结果进入模型上下文，内容要做净化与截断）。

---

## 9. 轻量手写实现参考（不依赖官方 SDK）

> 调研方法：GitHub/Sourcegraph 代码检索（`"Mcp-Session-Id"` 语言过滤）→ 逐仓库浅克隆 → 对核心文件实测 `wc -l`、读依赖清单、grep 各协议行为（Mcp-Session-Id、GET/405、Accept 校验、DELETE、协议版本串）。行数与行为均为 2026-09-09 实测，非文档转述。

### 9.1 真正"手写 Streamable HTTP"的仓库矩阵

| 仓库（语言） | 核心行数 | 运行时依赖 | 协议版本 | 会话/GET/405/DELETE/Accept 行为 |
|---|---|---|---|---|
| [mrexodia/zeromcp](https://github.com/mrexodia/zeromcp)（Python） | **2,187**（mcp.py 1,839 + jsonrpc.py 345） | **零依赖**（纯 stdlib `http.server`，PyPI v1.10.0；官方 `mcp` 仅作 dev 依赖用于一致性测试） | 2025-03-26（默认）/2025-06-18/2025-11-25 + 旧 SSE 2024-11-05（/sse） | ✅ initialize 签发 session（严格模式 400/404，LRU≤1024）；GET /mcp → **405**（无独立 GET 流）；❌ 无 Accept 校验；DELETE → 204/404/400；校验 `MCP-Protocol-Version` 头（400）；还带 CORS/OPTIONS、OAuth protected-resource metadata、JSON-only /mcp。88★，MIT，2026-09 活跃 |
| [trpc-group/trpc-mcp-go](https://github.com/trpc-group/trpc-mcp-go)（Go，腾讯） | ~2,000（streamable_server.go 852 + server.go 754） | kin-openapi, uuid, zap, uritemplate | 2024-11-05 + 2025-03-26 | ✅ 会话强制（非 init 缺头 400）；GET → 405 + `Allow: POST, DELETE`；✅ Accept 驱动 JSON/SSE；✅ DELETE 终止会话；通知 → 202；有 stateless 模式 |
| [ThinkInAIXYZ/go-mcp](https://github.com/ThinkInAIXYZ/go-mcp)（Go 社区 SDK） | streamable_http_server.go 422（pkg 全量 ~3k） | uuid, concurrent-map, gjson, uritemplate | 2025-03-26（兼容 2024-11-05） | ✅ 独立 GET SSE（stateless 模式下 GET → 405）；✅ Accept 校验（400 "Missing Accept header"）；✅ DELETE（stateless → 405）。676★，2026-08 活跃 |
| [cbrgm/go-mcp-server](https://github.com/cbrgm/go-mcp-server)（Go） | ~1,720（http.go 622 + server.go 423 + mcp/* ~430） | 零（`net/http`；仅 `go-arg` 做 CLI） | 2025-03-26 | ✅ 每会话 session store；✅ GET 开 SSE 流（默认 405 可选）；✅ Accept 校验；❌ DELETE。作者自述 "learning purposes" |
| [ckanthony/gin-mcp](https://github.com/ckanthony/gin-mcp)（Go） | **553**（pkg/transport/streamable_http.go） | gin, uuid, logrus | 2025-03-26 | ✅ 会话；可选 GET SSE；partial：Origin/DNS-rebinding 校验；❌ DELETE。78★ |
| [FreePeak/db-mcp-server](https://github.com/FreePeak/db-mcp-server) + [FreePeak/cortex](https://github.com/FreePeak/cortex)（Go） | **106 行** streamable.go（cortex 核心零外部依赖） | 无 | 2025-03-26 | ✅ init/tools；会话仅跟踪；POST-only（其它 405）；✅ Accept 驱动 JSON/SSE。**已知的"最小真实 Streamable HTTP 实现"**。422★，2026-08 活跃 |
| [okashoi/mcp-streamable-http-server-with-vanilla-php](https://github.com/okashoi/mcp-streamable-http-server-with-vanilla-php)（PHP） | **100 行**（单文件 mcp.php） | 零（无 Composer/框架） | 硬编码 2025-03-26 | ✅ init（固定响应）+ 1 个 demo 工具；❌ 会话/GET/DELETE/Accept 均无。教学级最小可跑示例 |

**次级参考（非 Streamable HTTP 或仅 stdio，但有价值）**：
- [zalez/perplexity-agent-mcp](https://github.com/zalez/perplexity-agent-mcp)（Python 单文件 1,774 行，纯 stdlib，**stdio-only**）——唯一发现覆盖 **2026-07-28 无状态时代**（`server/discover`、`_meta.protocolVersion`）的手写实现，兼支持 2025-11-25/2025-06-18/2025-03-26 协商，190 个测试。想看新时代手写逻辑就看它的 stdio 部分 + 第 7.2 节清单。
- [nacos-group/r-nacos](https://github.com/nacos-group/r-nacos)（Rust ≈1,550★）：`src/openapi/mcp/` 882 行手写 MCP 模块（api.rs 602 + sse.rs 180），2024-11-05 + 2025-03-26。
- [pguso/mcp-from-scratch](https://github.com/pguso/mcp-from-scratch)（JS，12 课零依赖纯 Node 教程，stdio，2025-11-25）。

### 9.2 为什么"手写 TS 服务器"很少——生态现实

知名 TS MCP 服务器全部建在官方 SDK 或其包装上：exa-mcp-server（4.5k★，经 `mcp-handler` 包装 SDK）、context7（`@modelcontextprotocol/server` v2 + express）、drawio-mcp-server（SDK+Hono）、mcp-framework（SDK 为 peer dep，其 HTTP 传输就是包了 `StreamableHTTPServerTransport`）、cloudflare/workers-mcp（647★）、[@hono/mcp](https://www.npmjs.com/package/@hono/mcp)（SDK peer）。**最好的"SDK 但不碰 Express"参考**：[mhart/mcp-hono-stateless](https://github.com/mhart/mcp-hono-stateless)（102★，190 行 src/index.ts，SDK 1.10.2 + Hono on Workers，无状态）。

### 9.3 SDK 的"去框架"路径（补强第 5 节）

- **TS v1**：`StreamableHTTPServerTransport.handleRequest(req, res, parsedBody?)` 直接吃 `node:http` 的 req/res（[v1.x 源码](https://github.com/modelcontextprotocol/typescript-sdk/blob/v1.x/src/server/streamableHttp.ts)）；Express 只出现在示例里。
- **TS v2**：`@modelcontextprotocol/node` = `NodeStreamableHTTPServerTransport` + `toNodeHandler` + `localhostHostValidation`/`localhostOriginValidation`（221 + 361 行）；裸 `node:http` 官方示例：[examples/elicitation/server.ts](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/examples/elicitation/server.ts)（用 `node:http` 的 `createServer`；另有 bearer-auth-web、gateway、scoped-tools 示例）。
- **Python v1/v2**：`run()` 内置 uvicorn（v1 硬依赖），但 `streamable_http_app()` 返回**纯 Starlette ASGI app**，可挂到任意 ASGI 宿主（v1 参考 [lyehe/porterminal](https://github.com/lyehe/porterminal) `mcp_adapter.py`，288★：FastAPI 挂 `/mcp` + `json_response=True`）；v2 在 server.py:1279 同模式。

### 9.4 选型结论

- **要"少依赖、几百行、可读"的参考源码**：Python → **zeromcp**（最完整的零依赖手写实现，行为逐条贴规范）；Go → trpc-mcp-go / ThinkInAIXYZ go-mcp（功能全）或 FreePeak 的 106 行 handler（最小真实实现）。
- **对本项目（FreeBSD + Node 22）的实际建议不变**：用官方 TS SDK（纯 JS、双时代、免维护传输层），把精力花在工具实现与安全层；手写仅当你需要极小体积或教学目的。

---

## 附：针对本项目的落地建议（综合判断）

1. **协议版本策略**：实现**双时代**单端点——旧时代语义（2025-06-18/2025-11-25：`initialize`+`ping`+`tools/list`+`tools/call`，无会话、纯 JSON 响应）为主，外加 2026-07-28 的无状态分支（校验 `_meta` + 标准头，支持 `server/discover`）。这正是官方 v2 `createMcpHandler(legacy:'stateless')` 与 Python v2 默认行为；若直接用 SDK 可零成本获得。
2. **运行时选型**：优先 **Node 22 + TS SDK**（无原生依赖；`StreamableHTTPServerTransport` 直连 `node:http`；`enableJsonResponse` + 无会话 = 最低内存占用）。Python 线在 FreeBSD 有 pydantic-core wheel 缺口风险（需 Rust 编译或系统包），不建议在无 root 共享主机上首选。
3. **形态参数**：无状态（不下发 `Mcp-Session-Id`）+ `enableJsonResponse: true` + 不实现 GET 流（对 GET 回 405——合规且被 2026 规范追认为唯一行为）。
4. **安全五件套**：Bearer 常量时间校验（401 + `WWW-Authenticate: Bearer resource_metadata=...`）、Origin 存在即白名单校验（403）、body ≤256KiB（413）、IP 速率限制（429）、请求级超时 + 工具级超时。
5. **不实现**：resumability/eventStore、`subscriptions/listen`、resources/prompts、tasks、 elicitation/sampling/roots（只读检索服务用不到；未声明 capability 即可）。
