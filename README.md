# API 部署套件

以 Docker Compose 一键部署 FastAPI 与 PostgreSQL 的后端服务，内含类似 Google Sheets 的浏览器管理界面。

## 前置条件

| 项目 | 要求 |
|---|---|
| Docker Engine / Docker Desktop | 已安装且正在运行 |
| Docker Compose | Compose v2（`docker compose`）|
| 系统资源 | 至少 4 GB 可用内存、约 1 GB 磁盘空间 |

主机无需安装 Python、Node.js 或 PostgreSQL；所有服务均在容器中执行。

## 快速开始

### Linux

```bash
chmod +x deploy.sh
./deploy.sh
```

脚本会验证 Docker 环境、在缺少时安全生成 `.env`、构建 API 镜像、启动服务、等待健康检查，并执行烟雾测试。API 默认位于 `http://localhost:8080`，Swagger 文档位于 `http://localhost:8080/docs`。

```bash
./deploy.sh --rebuild     # 不使用 Docker 构建缓存
./deploy.sh --no-smoke    # 跳过烟雾测试
```

### Windows

双击 `deploy.bat`，或在 PowerShell 执行：

```powershell
.\deploy.bat
.\deploy.bat --rebuild
.\deploy.bat --no-smoke
```

重复执行部署脚本是安全的：现有 `.env` 不会被覆盖，PostgreSQL 数据卷会保留。

## 服务与常用操作

| 操作 | Linux | Windows |
|---|---|---|
| 部署 | `./deploy.sh` | `.\deploy.bat` |
| 服务状态 | `docker compose ps` | `.\scripts\status.ps1` |
| 查看日志 | `docker compose logs --tail=100` | `.\scripts\logs.ps1` |
| 跟随日志 | `docker compose logs -f` | `.\scripts\logs.ps1 -Follow` |
| 停止服务（保留数据） | `docker compose stop` | `.\scripts\stop.ps1` |
| 停止并移除容器 | `docker compose down` | `.\scripts\stop.ps1 -RemoveContainers` |
| 备份数据库 | `docker compose exec -T db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > backup.dump` | `.\scripts\backup.ps1` |

## 配置

首次部署会生成 `.env`。若要手动配置，请从 `.env.example` 复制并填入：

```bash
cp .env.example .env
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `POSTGRES_DB` | `appdb` | 数据库名称 |
| `POSTGRES_USER` | `appuser` | 数据库账号 |
| `POSTGRES_PASSWORD` | 自动生成 | PostgreSQL 密码 |
| `API_PORT` | `8080` | 对外 API 端口 |
| `API_BIND_ADDRESS` | `127.0.0.1` | 监听地址；只有完成认证配置时才建议使用 `0.0.0.0` |
| `AUTH_MODE` | `ldap` | 认证方式；`disabled` 仅供隔离开发与自动化测试 |

修改 `.env` 后重新执行部署脚本即可套用配置。`.env` 包含敏感信息，已被 Git 忽略，切勿提交。

### LDAP 认证与权限

生产环境需要填写 `.env.example` 中的 LDAP 变量。应用会通过 LDAP 验证用户，并以签名、HttpOnly Cookie 维持会话；密码不会储存，也不会进行 LDAP 写入。

- `LDAP_ADMIN_GROUP_DN` 的成员可以访问全部工作表和管理控制台。
- `LDAP_SHEET_ACCESS_JSON` 可按 `xxx` 与 `settings` 工作表，针对 LDAP 群组或部门授予权限。
- 推荐使用 `ldaps://`；目前不支持 StartTLS 与嵌套群组解析。
- 任何必需 LDAP 配置缺失时，LDAP 模式会以 503 失败关闭。

示例：

```json
{
  "xxx": { "groups": ["cn=xxx-editors,ou=groups,dc=example,dc=com"] },
  "settings": { "departments": ["maintenance"] }
}
```

## 管理界面与 API

管理界面：`http://localhost:8080/`（或 `/admin`）；登录页：`/login`。浏览器只会调用同端口的 FastAPI，绝不会直接连至 PostgreSQL。

| 资源 | 端点 | 说明 |
|---|---|---|
| XXX 服务 | `/api/contract-services` | 建立、查询、更新、删除与 CSV 原子导入 |
| 用户设置 | `/api/user-settings` | 建立、查询、更新、删除用户设置 |
| 健康检查 | `/health` | 部署与监控使用 |

`/api/contract-services` 支持 `contract_no`、`q`、`limit`、`offset` 查询参数；`RBQ No.` 是服务行唯一标识。CSV 仅可由管理控制台导入，重复的 `RBQ No.` 会使整次导入失败。

## 架构

```text
docker-compose.yml
├── db：PostgreSQL 16.4-alpine
│   ├── 持久化卷：app-pgdata
│   └── 仅位于内部 Docker 网络
└── api：FastAPI / Python 3.12
    ├── 从 backend/Dockerfile 构建
    ├── 等待 db 健康后启动
    ├── 对外映射 ${API_PORT}:8000
    └── 通过 GET /health 健康检查
```

## 故障排除

**Docker 守护程序未运行**：启动 Docker Desktop（Linux 上启动 Docker 服务）后重新执行脚本。

**健康检查失败**：执行 `docker compose logs --tail=50 api` 查看 API 日志，并用 `docker compose ps` 查看容器状态。

**端口已被占用**：修改 `.env` 的 `API_PORT`，例如 `API_PORT=9090`，然后重新部署。

**需要局域网访问**：将 `API_BIND_ADDRESS` 改为 `0.0.0.0`，并仅在已配置认证与防火墙入站规则后开放对应 TCP 端口。
