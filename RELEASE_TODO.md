# VedicSign Release TODO

本文件是 VedicSign 面向公网发布前的唯一上线门禁清单。它关注“当前仓库是否已具备
可部署、可恢复、可观察、可安全收费的条件”，不替代产品功能清单 `TODO.md`。

每次准备发布时：

1. 从头检查所有 `BLOCKER` 项；
2. 在具体发布记录中保存 commit SHA、镜像 digest、数据库 migration 版本和验证结果；
3. 不因为“本地可以运行”而跳过认证、持久化、恢复和真实支付验证；
4. 未完成项保持 `[ ]`，完成后在条目下补充代码、测试或运行记录作为 evidence。

标记约定：

- `BLOCKER`：首次公开上线前必须完成；
- `REQUIRED`：每次生产发布必须满足；
- `FOLLOW-UP`：允许小范围公测后完成，但开始规模化收费前应完成；
- `AUTO`：最终应由脚本或 CI 自动检查；
- `MANUAL`：需要在域名、Clerk、Creem、Postgres 或 VPS 控制台人工确认。

## 1. 已确认的生产拓扑

### 1.1 域名

- [ ] `BLOCKER` `MANUAL` 选定唯一主域名：`vedicsign.ai` 或 `vedicsign.com`。
- [ ] `REQUIRED` `MANUAL` 另一个域名只做 301/308 跳转，避免出现两个可登录、可支付的
      canonical origin。
- [ ] `BLOCKER` Web 产品使用：
      `https://vedicsign.ai` 或 `https://vedicsign.com`。
- [ ] `BLOCKER` API 使用同一主域下的独立子域名：
      `https://api.vedicsign.ai` 或 `https://api.vedicsign.com`。
- [ ] `REQUIRED` Creem webhook 指向稳定 API 域名，例如：
      `https://api.vedicsign.ai/webhooks/creem`。

采用独立 API 子域名是本项目的正式部署方向。它比把 API 暴露为 Web 域名下的
`/api` 更适合后续独立限流、日志、WAF、缓存策略和扩容，但同时引入 CORS、两个 DNS
记录和两个 HTTPS origin。仓库必须显式支持这些差异。

建议公开 API 结构：

```text
https://api.vedicsign.ai/health
https://api.vedicsign.ai/v1/places
https://api.vedicsign.ai/v1/skill-sessions
https://api.vedicsign.ai/v1/core-jobs
https://api.vedicsign.ai/v1/billing/checkout
https://api.vedicsign.ai/webhooks/creem
```

`/v1` 用于产品 API；health 和第三方 webhook 不必放进版本前缀。首次发布前可以保留
后端内部 `/api/*` 路由并由反向代理改写，但浏览器看到的公开 URL 和前端配置应遵守
上面的域名约定。长期应使用 FastAPI `APIRouter` 统一管理公开前缀，避免在 Caddy 中
维护大量逐路由 rewrite。

### 1.2 单 VPS 初始形态

```text
Internet
  -> Caddy :80/:443
       -> vedicsign.ai       -> production frontend
       -> api.vedicsign.ai   -> FastAPI container :8787
                                  -> managed PostgreSQL URL
                                  -> durable session artifact volume
                                  -> Clerk / Creem / LLM provider
```

- [ ] `BLOCKER` 生产只选择 Caddy 作为反向代理和 TLS 终止层；首版不同时维护 Nginx。
- [ ] `BLOCKER` PostgreSQL 通过 `DATABASE_URL` 连接外部/托管实例，生产 Compose 不负责
      在同一 VPS 内启动数据库。
- [ ] `BLOCKER` `backend/data/sessions` 使用独立持久卷或宿主机数据目录，容器重建不丢失。
- [ ] `BLOCKER` FastAPI 只在 Docker 内网监听；VPS 公网仅开放 80/443 和受限 SSH。
- [ ] `BLOCKER` 当前任务状态仍依赖进程内存时，只运行一个 FastAPI worker 和一个 API
      replica。禁止通过多个 Uvicorn worker 做伪扩容。

## 2. 期望的仓库部署接口

最终从一台干净 VPS 开始，操作应收敛为：

```bash
git clone <github-repository-url> vedicsign
cd vedicsign
./deploy.sh setup
```

后续更新应收敛为：

```bash
cd vedicsign
./deploy.sh
```

高级或自动化场景使用同一个入口：

```bash
./deploy.sh doctor
./deploy.sh --dry-run
./deploy.sh --ref <commit-sha>
./deploy.sh rollback
./deploy.sh status --json
```

`deploy.sh` 是面向操作者的唯一公开入口。内部仍拆分为可测试的小脚本，但用户无需记住
bootstrap、configure、doctor、backup、smoke-test 等脚本的路径。

目标文件结构：

```text
Dockerfile
compose.production.yml
.env.production.example
deploy.sh                         # 唯一公开 CLI；无子命令时执行常规更新
deploy/
  Caddyfile
  prometheus.yml                 # 若启用本机 monitoring profile
scripts/production/
  bootstrap.sh                   # setup 内部步骤；一台 VPS 通常只运行一次
  configure.sh                   # setup 内部步骤；生成/更新生产配置
  doctor.sh                      # 不改状态的环境与配置诊断
  release.sh                     # 可重复、可回滚的日常发布实现
  smoke-test.sh                  # 域名/API/登录/基础工作流检查
  backup.sh                      # artifact 备份；DB 备份由供应商或脚本触发
  restore-check.sh               # 在隔离目录验证备份可恢复
  rollback.sh                    # 回到上一已知可用镜像/commit
```

### 2.1 CLI 交互体验

首次 setup 参考成熟安装器的交互结构，但增加生产部署特有的风险门禁：

```text
VedicSign Production Setup

✓ Environment detected
  Ubuntu 24.04 · x86_64 · Docker 27 · Compose 2.x

✓ Source
  repository: github.com/<owner>/<repo>
  ref: main @ <commit-sha>

! Configuration
  Web:      https://vedicsign.ai
  API:      https://api.vedicsign.ai
  Database: PostgreSQL configured (secret hidden)
  Clerk:    configured
  Creem:    test mode
  Agent:    DeepSeek-compatible runtime configured

! Release risk assessment
  Database migration: pending
  Active jobs: 0
  Backup: ready
  Blocking checks: 0

Deploy this configuration? (Y/n)
```

- [ ] `BLOCKER` `AUTO` 自动检测 OS、架构、Docker、Compose、Git、当前 commit、已有配置和
      当前服务状态，避免重复询问可可靠探测的信息。
- [ ] `BLOCKER` 执行前集中展示 source、domains、非敏感配置摘要、将创建/修改的资源和风险，
      不把关键信息分散在大量连续问题中。
- [x] `BLOCKER` secret 使用隐藏输入；摘要只显示 `configured`、`missing` 或脱敏尾部字符。
      Evidence: `scripts/production/configure.sh` 及 deploy CLI 自测中的输出泄露检查。
- [ ] `BLOCKER` 把检查结果分成 passed、warning、manual action 和 blocking error；blocking error
      不允许通过普通确认强行跳过。
- [ ] `REQUIRED` 长步骤显示当前阶段和耗时：fetch、build、migration、start、health、smoke；
      失败时保留完整日志文件并在终端显示简短原因和修复命令。
- [ ] `REQUIRED` 完成摘要列出已部署版本、访问地址、服务状态、回滚点及仍需去外部控制台完成的
      Clerk/Creem/DNS 动作。
- [ ] `REQUIRED` setup 可中断后重跑；已经完成且校验通过的步骤显示为 detected/ready，不重复
      破坏性执行。
- [ ] `REQUIRED` 支持 `--yes` 非交互模式，但只有配置完整且没有 warning/blocker 时才允许；
      生产默认仍在变更前要求确认。
- [ ] `REQUIRED` 支持 `--dry-run`，只完成探测、配置校验、release plan 和风险摘要，不 pull、
      build、migration 或 restart。
- [ ] `REQUIRED` 支持 `--json` 输出机器可读状态；ANSI 颜色、spinner 和交互提示仅在 TTY 中启用。
- [ ] `REQUIRED` 固定退出码：配置错误、构建失败、migration 失败、health 失败、smoke 失败各自
      可区分，方便 CI 或远程运维判断。

### 2.2 首次 VPS bootstrap

- [x] `BLOCKER` `AUTO` 新增 `scripts/production/bootstrap.sh`，可重复运行且不会破坏已有环境。
- [x] `REQUIRED` 检查 Linux 发行版和 CPU 架构；首版明确支持 Ubuntu LTS x86_64。
- [x] `REQUIRED` 安装或验证 Docker Engine、Compose plugin、Git、curl 和基础证书工具。
- [x] `REQUIRED` 创建生产目录，例如 `/opt/vedicsign`、`/var/lib/vedicsign/sessions`、
      `/var/backups/vedicsign`，并设置最小权限。
- [x] `REQUIRED` 配置 Docker 日志轮转，防止日志耗尽磁盘。
- [ ] `REQUIRED` 检查 80/443 是否可用；指导用户配置云厂商 security group 和 UFW。
- [ ] `REQUIRED` 检查 DNS 是否已经把 Web/API 域名解析到当前 VPS；未生效时给出明确指导，
      不伪装成部署成功。
- [x] `REQUIRED` 不自动修改 SSH 登录策略或删除已有防火墙规则；输出加固建议并要求人工确认。
- [ ] `REQUIRED` 脚本的每个系统级变更都应打印将要执行的命令，并在需要 `sudo` 时明确提示。

### 2.3 交互式生产配置

- [x] `BLOCKER` `AUTO` 新增 `.env.production.example`，只包含变量名、说明和安全默认值，
      不含真实密钥。
- [x] `BLOCKER` `AUTO` 新增 `scripts/production/configure.sh`，交互式收集或确认配置。
- [ ] `REQUIRED` 已有配置再次运行时默认保留原值；secret 不回显，不写入 shell history。
- [x] `REQUIRED` 生成的生产环境文件权限为 `0600`，并已被 Git 忽略。
      Evidence: `.gitignore` 精确忽略真实配置、保留模板，deploy CLI 自测验证文件 mode。
- [ ] `REQUIRED` 将变量区分为 build-time 和 runtime；修改 `VITE_*` 后必须触发前端重建。
- [ ] `REQUIRED` 配置脚本结束后自动调用 `doctor.sh`，列出缺失、格式错误和待人工配置项。

至少需要收集以下配置：

```dotenv
# Deployment identity
APP_ENV=production
SITE_DOMAIN=vedicsign.ai
API_DOMAIN=api.vedicsign.ai
ALLOWED_ORIGINS=https://vedicsign.ai

# Frontend build-time configuration
VITE_API_BASE_URL=https://api.vedicsign.ai/v1
VITE_CLERK_PUBLISHABLE_KEY=

# Backend and authentication
VEDIC_AUTH_MODE=clerk
CLERK_SECRET_KEY=
VEDIC_ADMIN_USER_IDS=
VEDIC_ADMIN_EMAILS=
HOST=0.0.0.0
PORT=8787
RELOAD=false

# Persistent database
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
DATABASE_ECHO=false

# Agent runtime
DEEPSEEK_API_KEY=
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_MODEL=
ANTHROPIC_DEFAULT_OPUS_MODEL=
ANTHROPIC_DEFAULT_SONNET_MODEL=
ANTHROPIC_DEFAULT_HAIKU_MODEL=
AGENT_EFFORT=max
AGENT_MAX_TURNS=8
AGENT_TIMEOUT_MS=420000

# Optional place provider
AMAP_WEB_SERVICE_KEY=
AMAP_PLACE_FALLBACK_ENABLED=false

# Billing
CREEM_API_KEY=
CREEM_WEBHOOK_SECRET=
CREEM_TEST_MODE=true
CREEM_SUCCESS_URL=https://vedicsign.ai/account?billing=success
CREEM_PRODUCT_PRO_MONTHLY=
CREEM_PRODUCT_PRO_YEARLY=
CREEM_PRODUCT_SINGLE_REPORT=
```

- [ ] `BLOCKER` `doctor.sh` 验证 URL scheme、域名配对、布尔值、端口、必需密钥是否非空。
- [x] `BLOCKER` `doctor.sh` 检查 `CREEM_SUCCESS_URL` 与 `SITE_DOMAIN` 一致。
- [x] `BLOCKER` `doctor.sh` 检查生产环境不是 `VEDIC_AUTH_MODE=disabled` 或
      `VEDIC_AI_MODE=mock`。
- [x] `BLOCKER` `doctor.sh` 只报告密钥是否存在和必要的前后缀，不输出完整 secret 或
      `DATABASE_URL` 密码。
- [ ] `REQUIRED` 支持测试支付和真实支付两个清晰配置阶段；不允许只改 API key 却忘记
      `CREEM_TEST_MODE`、product IDs 或 webhook secret。

### 2.4 Docker 构建

- [x] `BLOCKER` `AUTO` 新增多阶段生产 `Dockerfile`，所有依赖使用 lockfile 安装。
- [x] `BLOCKER` 前端执行 `npm ci`、TypeScript 检查和 `vite build`，产物不依赖 Vite dev server。
- [x] `BLOCKER` 后端使用 Python 3.11 和 `backend/uv.lock`，并执行 astrology runtime setup。
- [x] `BLOCKER` 镜像包含并验证 `backend/astrology-runtime.lock`、PyJHora 数据和 Swiss
      Ephemeris 文件。
- [ ] `BLOCKER` 因 PDF 下载会调用 Node + Playwright，后端运行镜像必须包含 Node、
      Playwright Chromium 及其系统依赖；构建阶段应运行一次最小 PDF smoke test。
- [ ] `REQUIRED` 最终运行用户不是 root；镜像内代码只读，只有 session/artifact 目录可写。
- [x] `REQUIRED` 添加 `.dockerignore`，排除 `.git`、`.env*`、`node_modules`、本地 venv、
      `backend/data`、测试浏览器缓存和生成报告。
- [ ] `REQUIRED` 镜像带 OCI labels：commit SHA、构建时间、版本和 repository URL。
- [x] `REQUIRED` 为 frontend/Caddy 和 backend 选择清晰方案并固定下来：
      要么分别构建两个镜像，要么由同一 release 构建导出 frontend artifact；不得在 VPS
      裸机执行长期运行的 Node 服务。

### 2.5 Compose 与 Caddy

- [x] `BLOCKER` `AUTO` 新增 `compose.production.yml`，至少包含 Caddy 和 FastAPI 服务。
- [x] `BLOCKER` 只有 Caddy 映射宿主机 80/443；FastAPI 仅通过 Compose network 暴露 8787。
- [x] `BLOCKER` Caddy 为 Web 和 API 两个域名自动申请并续期 TLS 证书。
- [x] `BLOCKER` Web 域名提供 Vite 静态文件，并将未知前端路径回退到 `index.html`。
- [x] `BLOCKER` API 域名只反代 FastAPI，不提供前端文件。
- [ ] `BLOCKER` Caddy 正确转发客户端 IP、scheme、host 和 request ID。
- [ ] `REQUIRED` 配置 gzip/zstd、安全响应头、合理的请求体大小和超时。
- [x] `REQUIRED` HTML 不长缓存；带 hash 的静态资源使用 immutable 长缓存。
- [ ] `REQUIRED` Caddy access log 使用 JSON、脱敏 query/header，并限制保留周期。
- [ ] `REQUIRED` Compose 配置容器 restart policy、healthcheck、日志大小和资源上限。
- [ ] `REQUIRED` Caddy 配置检查与 Compose config 检查进入 CI。

## 3. 当前代码上线 BLOCKER

### 3.1 前后端独立域名支持

- [ ] `BLOCKER` 将前端 API 调用从硬编码相对 `/api/...` 改为统一 API client，并读取
      `VITE_API_BASE_URL`。
- [ ] `BLOCKER` 对 base URL 做规范化，避免双斜线，并只允许 `http://localhost` 开发值或
      `https://` 生产值。
- [ ] `BLOCKER` Vite 本地开发仍可使用 proxy，但生产构建不能依赖 `vite.config.ts` proxy。
- [ ] `BLOCKER` FastAPI CORS origins 改为读取 `ALLOWED_ORIGINS`，生产只允许确切 Web origin，
      不使用 `*`。
- [ ] `BLOCKER` CORS 允许 `Authorization`、`Content-Type`、`x-vedic-anonymous-id`，并验证
      OPTIONS preflight。
- [ ] `BLOCKER` Clerk Dashboard 配置 Web 生产域名的 allowed origins、redirect URLs 和
      authorized parties。
- [ ] `BLOCKER` 添加测试：允许生产 Web origin，拒绝未知 origin，认证请求可跨域成功。

### 3.2 认证与授权

- [ ] `BLOCKER` 当前 Clerk JWT 验证必须从“未验签 payload + Clerk user lookup”改为 Clerk
      JWKS 公钥验签。
- [ ] `BLOCKER` 验证 JWT signature、`exp`、`nbf`、`iss`、`azp`/authorized party，以及适用的
      `aud`；缓存 JWKS 并处理 key rotation。
- [ ] `BLOCKER` 添加伪造签名、篡改 `sub`、过期 token、错误 issuer、错误 authorized party、
      普通用户访问 admin API 的负向测试。
- [ ] `BLOCKER` 管理员权限只来自服务端明确 allowlist 或可信 Clerk metadata；生产环境不能为空
      或误配为公共邮箱域。
- [ ] `REQUIRED` 审核匿名 session 创建、登录后 claim、跨用户读取、PDF 下载的完整授权路径。
- [ ] `REQUIRED` `/api/health` 目前暴露本机路径和运行配置；公开 health 必须只返回最小状态，
      深度诊断接口只能管理员访问或仅在容器内访问。

### 3.3 后台任务可靠性

- [ ] `BLOCKER` 当前 `CoreJobRuntime` 的 job registry 与 `asyncio.Task` 在内存中；明确首发策略：
      发布/重启前 drain 活跃任务，单 worker，重启后把遗留 running job 标记为 interrupted 并允许
      从已有 checkpoint 安全重试。
- [ ] `BLOCKER` 前端对 interrupted、failed、timeout、retrying 有明确状态和操作，不永久轮询
      已不存在的内存 job。
- [ ] `BLOCKER` 单 session 同一时刻只能有一个核心任务；幂等保护必须落在持久数据库，而不仅是
      当前进程字典。
- [ ] `BLOCKER` `MAX_CONCURRENCY=10` 改为环境配置，并加入单用户、单进程、全局模型调用并发限制。
- [ ] `FOLLOW-UP` 将 API 与 worker 分离，使用 Redis-backed queue 或同等级持久任务系统。
- [ ] `FOLLOW-UP` 实现重试退避、取消、暂停/恢复、dead-letter 和跨部署任务恢复。

### 3.4 数据库和存储

- [ ] `BLOCKER` 引入 Alembic 或同等级 migration；停止依赖生产启动时 `create_all()` 和临时
      `ALTER TABLE` 作为正式 schema 变更机制。
- [ ] `BLOCKER` 从空 PostgreSQL 执行全部 migration 并通过 backend startup、auth、billing、
      session metadata 测试。
- [ ] `BLOCKER` session artifact 卷写入、读取、PDF 导出和容器重建保留测试通过。
- [ ] `BLOCKER` 建立数据库每日备份和异地 artifact 备份；记录保留周期、加密方式和恢复步骤。
- [ ] `BLOCKER` 至少完成一次隔离环境恢复演练，并记录实际 RPO/RTO。
- [ ] `FOLLOW-UP` 将 artifacts 抽象为 repository，迁移到 S3/R2 等对象存储；数据库保存 object key
      和校验值。

### 3.5 成本、安全和隐私

- [ ] `BLOCKER` 对匿名创建、登录 API、报告启动、轮询、地点搜索、PDF 导出分别限流。
- [ ] `BLOCKER` 付费报告操作必须在服务端验证 entitlement；前端显示状态不能作为授权依据。
- [ ] `BLOCKER` Creem webhook 验签、事件幂等、重复投递、乱序、退款和 dispute 测试通过。
- [ ] `BLOCKER` 给输入正文、反馈、query、请求体和上传内容设置长度/大小上限。
- [ ] `BLOCKER` 日志中不记录 Clerk token、LLM key、数据库密码、Creem signature、完整出生资料
      或完整报告正文。
- [ ] `BLOCKER` 发布隐私政策、服务条款、退款政策和占星服务免责声明。
- [ ] `BLOCKER` 定义 session/report 保存周期，实现用户删除账户数据和管理员审计。
- [ ] `REQUIRED` 所有面向用户的 5xx 不返回内部路径、provider response、stack trace 或 secret。

## 4. `deploy.sh` 发布契约

`deploy.sh` 是后续唯一日常发布入口。它必须可重复运行、遇错停止、保留上一版本，并且不会
覆盖用户手工维护的生产环境文件。

- [x] `BLOCKER` `AUTO` 实现统一命令路由：`setup`、`doctor`、默认 `deploy`、`status`、
      `rollback`、`backup`、`restore-check`；`--help` 对每个命令给出示例和风险说明。
- [ ] `BLOCKER` `AUTO` 默认部署配置的 release branch（建议 `main`），支持 `--ref <sha|tag|branch>`。
- [ ] `REQUIRED` 支持 `--dry-run`、`--yes`、`--json`；危险选项必须使用完整、难误触的名字，
      不提供含义模糊的单字母强制参数。
- [x] `REQUIRED` 开始前检查 Git worktree；存在本地修改时拒绝自动 pull，不覆盖 VPS 文件。
- [x] `REQUIRED` 使用 `git fetch` + 明确 ref + fast-forward 规则；记录 before/after SHA。
- [ ] `REQUIRED` 运行 `doctor.sh`、`docker compose config` 和 Caddy config validation。
- [x] `REQUIRED` 构建内容寻址或带 SHA tag 的镜像，不只使用不可追踪的 `latest`。
- [x] `REQUIRED` 构建失败时保持旧服务运行。
- [ ] `REQUIRED` migration 前确认数据库可达并创建发布前备份/快照；migration 失败时停止切换。
- [x] `REQUIRED` 启动新版本后等待 Docker healthcheck，并从 VPS 本机和公网域名执行 smoke tests。
- [x] `REQUIRED` smoke test 失败时自动回滚应用镜像；数据库 migration 是否回滚必须由 migration
      策略明确决定，不能盲目 downgrade。
- [ ] `REQUIRED` 发布期间检测活跃 core jobs；在任务仍是进程内实现时拒绝立即重启，除非显式
      `--force-interrupt-jobs` 并打印影响。
- [ ] `REQUIRED` 成功后清理旧镜像但至少保留上一已知可用版本；不得执行无边界 Docker prune。
- [x] `REQUIRED` 输出简洁发布摘要：版本、SHA、耗时、migration、health、smoke、回滚点。
- [x] `REQUIRED` 部署脚本不得打印 `.env.production` 内容或把 secret 作为命令行参数暴露给
      process list。

## 5. 自动验证与 smoke test

### 5.1 CI release gate

- [ ] `BLOCKER` 现有代码质量、类型检查、后端测试和前端 build 全部通过。
- [ ] `BLOCKER` CI 构建生产 Docker image，而不仅是宿主机 Node/Python build。
- [ ] `BLOCKER` 在容器内运行 backend runtime/preflight，确认 astrology 依赖和数据完整。
- [ ] `BLOCKER` 在容器内渲染一份最小 PDF。
- [ ] `BLOCKER` 对 Compose、Caddy、`.env.production.example` 完整性做静态检查。
- [ ] `BLOCKER` 扫描依赖漏洞、误提交 secret 和镜像中的高危 CVE；阻止 critical 漏洞发布。
- [ ] `REQUIRED` release tag/commit 对应的测试结果、镜像 digest 可追溯。

### 5.2 无密钥公网 smoke test

- [ ] `REQUIRED` `https://vedicsign.<tld>/` 返回 200 且没有 mixed content。
- [ ] `REQUIRED` 直接刷新 `/account`、`/session/<id>` 等 SPA route 不返回 Caddy 404。
- [ ] `REQUIRED` `https://api.vedicsign.<tld>/health` 返回最小健康响应。
- [ ] `REQUIRED` Web 和 API TLS 证书、hostname、有效期均正确。
- [ ] `REQUIRED` 未知 CORS origin 不获得允许头；正式 Web origin 的 OPTIONS preflight 成功。
- [ ] `REQUIRED` 未认证访问账户、付费报告、admin API 返回正确的 401/403。
- [ ] `REQUIRED` 静态资源缓存、HTML 缓存、security headers 符合配置。

### 5.3 带测试账户的受保护 smoke test

- [ ] `BLOCKER` `MANUAL` Clerk 注册、登录、刷新、退出和过期 session 行为正确。
- [ ] `BLOCKER` `MANUAL` 匿名创建 session 后登录，session 被正确 claim 且其他账户不可访问。
- [ ] `BLOCKER` `MANUAL` Creem test checkout 完成后 webhook 更新 entitlement。
- [ ] `BLOCKER` `MANUAL` 完整执行一次：出生信息 -> calculation -> core job -> report -> PDF。
- [ ] `BLOCKER` `MANUAL` 记录报告总耗时、每阶段耗时、模型调用次数和估算成本。
- [ ] `BLOCKER` `MANUAL` 退款/取消后权限按产品规则变化，重复 webhook 不重复授予权益。

## 6. 监控、日志与告警

- [x] `BLOCKER` Docker healthcheck 覆盖 Caddy 和 FastAPI；health 不依赖会产生费用的 LLM 调用。
- [ ] `BLOCKER` 外部 uptime monitor 同时检查 Web 首页和 API health，避免“容器活着但 DNS/TLS
      已坏”未被发现。
- [ ] `REQUIRED` 采集 VPS CPU、内存、磁盘、inode、load、容器 restart count 和证书状态。
- [ ] `REQUIRED` 采集 API 5xx/429、请求耗时、活跃任务、任务失败、LLM timeout/rate limit、
      PDF failure 和 Creem webhook failure。
- [ ] `REQUIRED` 结构化日志带 request ID、session ID、job ID、node ID 和耗时；用户 ID 需要
      最小化或散列显示。
- [ ] `REQUIRED` 设置磁盘、服务不可达、5xx 激增、任务连续失败、webhook 连续失败告警。
- [ ] `REQUIRED` 告警目标通过配置选择 email、飞书或其他渠道；脚本只能验证配置，不能替用户
      创建外部账号。
- [ ] `FOLLOW-UP` 提供可选 Compose monitoring profile；如果部署 Prometheus/Grafana/Uptime
      Kuma，管理 UI 默认不公开到公网，只能通过 SSH tunnel/VPN 或额外认证访问。

## 7. 人工控制台配置

这些动作无法仅靠仓库脚本安全完成，`configure.sh` 应逐项提示并提供验证结果。

### 7.1 DNS

- [ ] `MANUAL` Web 主域 A/AAAA 指向 VPS。
- [ ] `MANUAL` `api` 子域 A/AAAA 指向 VPS。
- [ ] `MANUAL` 备用 `.com`/`.ai` 域名设置 redirect host 或 Caddy redirect site。
- [ ] `MANUAL` 若启用 Cloudflare proxy，确认 webhook、TLS mode、缓存和真实客户端 IP 设置。

### 7.2 Clerk

- [ ] `MANUAL` 使用 production instance 和 production keys。
- [ ] `MANUAL` 配置 Web origin、redirect URL、authorized party、邮件和登录方式。
- [ ] `MANUAL` 确认 API 子域不是用户登录 redirect target，Bearer token 由 Web origin 发往 API。
- [ ] `MANUAL` 添加明确的首位管理员 user ID，并用普通账户验证 admin API 被拒绝。

### 7.3 Creem

- [ ] `MANUAL` 先使用 test mode 产品和 webhook 做完整验证。
- [ ] `MANUAL` webhook URL 使用 API 子域，订阅所需 checkout/subscription/refund/dispute 事件。
- [ ] `MANUAL` 验证 test mode 后再创建 live keys、live products 和 live webhook secret。
- [ ] `MANUAL` 切换 live 时四项同时核对：mode、API key、product IDs、webhook secret。

### 7.4 PostgreSQL

- [ ] `MANUAL` 创建生产数据库和最小权限应用用户。
- [ ] `MANUAL` 开启 TLS、备份、PITR（若供应商支持）、连接数和费用告警。
- [ ] `MANUAL` 将 VPS 出站 IP 加入 allowlist（若数据库供应商支持）。
- [ ] `MANUAL` 保存独立的管理员恢复凭据，应用容器只使用非管理员连接串。

## 8. 上线与回滚演练

- [ ] `BLOCKER` 在 staging VPS 从全新 clone 完整执行一次 `./deploy.sh setup`。
- [ ] `BLOCKER` 在不重新输入 secret 的情况下再次运行 `deploy.sh`，确认幂等更新成功。
- [ ] `BLOCKER` 人为构造新版本 healthcheck 失败，确认旧版本仍可用或能自动回滚。
- [ ] `BLOCKER` 报告生成中尝试发布，确认 deploy 脚本会 drain/拒绝重启并给出原因。
- [ ] `BLOCKER` 删除测试容器后重建，确认数据库、session artifacts 和 Caddy certificates 保留。
- [ ] `BLOCKER` 从异地备份恢复一条完整 session 及其 PDF，并验证 owner access。
- [ ] `REQUIRED` 写明紧急回滚命令、值班联系人、数据库恢复入口和第三方 status page。

## 9. 首次发布 Go/No-Go

只有以下条件全部满足才可公开收费：

- [ ] 所有 `BLOCKER` 已完成并有 evidence；
- [ ] 生产 JWT 已执行完整密码学验签；
- [ ] 生产 PostgreSQL migration、备份和恢复演练完成；
- [ ] core job 在发布/重启时不会静默丢失，且有安全重试路径；
- [ ] 独立 Web/API 域名、CORS、Clerk 和 Creem 已在生产相同拓扑验证；
- [ ] 完整付费报告与 PDF 流程成功；
- [ ] 限流、成本上限、日志脱敏、隐私与删除政策生效；
- [ ] monitoring、外部 uptime 和关键告警已收到一次测试告警；
- [ ] `./deploy.sh` 和 `./deploy.sh rollback` 已在 staging 实际演练。

发布记录建议单独保存在 GitHub Release、部署系统或 `releases/` 外部运维目录，不要把
生产 secret、数据库 URL 或真实用户数据写进本文件。
