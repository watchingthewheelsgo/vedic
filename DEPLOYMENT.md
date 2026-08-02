# VedicSign VPS 部署指南

本指南用于把 VedicSign 从一个干净的 GitHub checkout 部署到单台 Ubuntu VPS。部署 CLI
会探测服务器环境、引导填写生产配置、构建 Web/后端镜像、启动 Caddy，并验证公网 Web
和 API 域名。

## 连接 VPS 前

先准备好：

- 一个 canonical 主域名，例如 `vedicsign.ai`；
- `vedicsign.ai` 和 `api.vedicsign.ai` 指向 VPS 的 DNS A/AAAA 记录；
- 启用 TLS 的托管 PostgreSQL URL；
- Clerk production publishable key 和 secret key；
- DeepSeek 或 Anthropic-compatible agent token、base URL 和模型名；
- 首次使用 Creem test credentials，完整验证后再换 live credentials。

首个明确支持的服务器环境是 Ubuntu LTS x86_64。云防火墙应允许 TCP 80/443、UDP 443
和来源受限的 SSH。脚本不会自动修改 SSH 或防火墙规则。

## 首次部署

使用普通、具有 sudo 权限的部署用户登录 VPS：

```bash
git clone <github-repository-url> vedicsign
cd vedicsign
./deploy.sh setup
```

`setup` 会依次：

1. 探测 OS、CPU 架构、Git、Docker 和 Compose；
2. Docker 缺失时，询问是否从 Docker 官方 apt repository 安装；
3. 逐步收集生产配置，secret 输入不会回显；
4. 以 `0600` 权限生成 `.env.production`；
5. 创建持久化 session 和 backup 目录；
6. 运行 release doctor，存在安全或 readiness blocker 时停止；
7. 构建带 Git SHA tag 的 Docker 镜像；
8. 启动 FastAPI 和 Caddy；
9. 验证容器健康、公网 HTTPS、API health 和生产 CORS。

如果本次刚安装 Docker，当前 shell 可能还没有获得 docker group 权限。CLI 会明确停止；
退出 SSH、重新登录，然后再次执行 `./deploy.sh setup`。Setup 可以重复执行，并默认保留
已有配置。

脚本不会打印完整 secret 或 PostgreSQL 密码，也不会提交或上传 `.env.production`。

## 必须人工完成的控制台配置

公网 smoke test 通过前，需要确认：

- Clerk 允许 `https://vedicsign.ai` 作为 Web origin 和 authorized party；
- Clerk redirect URLs 使用 canonical Web 域名；
- Creem success URL 是 `https://vedicsign.ai/account?billing=success`；
- Creem webhook 是 `https://api.vedicsign.ai/webhooks/creem`；
- 两个 DNS 记录都已在公网解析到 VPS，使 Caddy 可以签发证书。

如果最终选择 `.com`，将所有 `.ai` 替换成 `.com`。

## Readiness 和 dry run

以下命令不会修改 Git、镜像、数据库或容器：

```bash
./deploy.sh doctor
./deploy.sh doctor --json
./deploy.sh --dry-run
./deploy.sh status
```

Doctor 检测到 JWT 未验签、生产 CORS/API origin 未适配、缺少数据库 migration、Compose
无效或 secret 不完整时，会主动阻止发布，而不是绕过风险继续启动公网服务。

## 后续更新

在 VPS 的干净 checkout 中执行：

```bash
cd vedicsign
./deploy.sh
```

默认更新流程会 fetch `main`、只允许 fast-forward、构建带 Git SHA 的镜像、备份本地
session artifacts、执行 Alembic migration、启动新版本并运行 smoke tests。上一版本应用镜像
会作为 rollback target 保留。

也可以部署指定 commit 或 tag：

```bash
./deploy.sh --ref <commit-sha-or-tag>
```

VPS checkout 必须保持干净。生产配置和部署状态已经 Git-ignore；不要直接在 VPS 修改 tracked
source code。

## 回滚和备份

```bash
./deploy.sh backup
./deploy.sh restore-check
./deploy.sh rollback
```

Rollback 只切换应用镜像，不自动 downgrade 数据库。因此 migration 必须向前/向后兼容上一版
应用，或另有经过验证的数据库恢复方案。

Artifact archive 写入 `BACKUP_DIR`。PostgreSQL 是外部托管服务，需要在供应商处启用
backup/PITR，并单独演练恢复。

## 持久目录和日志

默认目录：

```text
/var/lib/vedicsign/sessions   生成的 session/report artifacts
/var/backups/vedicsign       本地 artifact archives
./.deploy                    release 状态和详细部署日志
```

常用诊断命令：

```bash
./deploy.sh status
docker compose --env-file .env.production -f compose.production.yml ps
docker compose --env-file .env.production -f compose.production.yml logs --tail=200 backend
docker compose --env-file .env.production -f compose.production.yml logs --tail=200 web
```

不要把 `.env.production`、authorization header、webhook signature 或完整用户报告粘贴到
issue、聊天或支持请求中。
