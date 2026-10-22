# 生产部署说明

面向当前这台阿里云 ECS（`aliyun`，39.104.226.135）。整套系统跑在 Docker 里，
浏览器只访问 **一个端口 80**：前端静态文件与 `/api`、`/uploads`、`/health` 共用同一个源，
因此没有跨域问题。

## 访问地址

| 用途 | 地址 |
| --- | --- |
| 系统首页 | http://39.104.226.135/ |
| 健康检查 | http://39.104.226.135/health/live 、/health/ready |
| 接口前缀 | http://39.104.226.135/api/... |

## 拓扑

```
浏览器
  │  :80
  ▼
ai-lab-web (nginx:alpine)
  ├── /            静态文件，来自 /opt/ai-lab/web/dist（Vue SPA，history 模式回落 index.html）
  └── /api /uploads /health  ──反代──▶ ai-lab-api (uvicorn :8000，不对外暴露)
                                            │
                                            │ ai-postgres-net
                                            ▼
                                     ai-postgres (已有 pgvector/pg17 容器，数据未迁移)
```

- 后端镜像：`ai-lab-api:1.0.0`，基于 `python:3.13-slim`，依赖由 `requirements.txt` 固定版本。
- 单进程 uvicorn：知识库 Worker 与预约自动审核任务都在进程内运行，多进程会重复执行，**不要加 `--workers`**。
- `APP_ENV=production`，因此 `/docs`、`/redoc`、`/openapi.json` 按代码设计关闭；需要调试时临时改 `api.env`。

### 网络寻址不使用容器 DNS

这条链路特意做成"零 DNS"，因为这台机器 I/O 被打满时 dockerd 会来不及应答内嵌 DNS，
曾导致应用报 `failed to resolve host 'ai-postgres': Temporary failure in name resolution`：

| 链路 | 寻址方式 | 配置位置 |
| --- | --- | --- |
| nginx → api | 固定 IP `10.211.0.10:8000` | `compose.yaml` 的 `api.ipv4_address` + `nginx.conf` 的 upstream |
| api → postgres | `/etc/hosts` 覆盖 `ai-postgres=10.210.1.2` | `compose.yaml` 的 `api.extra_hosts` |

改 IP 时两处必须同步；`ai-postgres` 若被重建导致 IP 变化，也要更新 `extra_hosts`。

## 服务器目录

```
/opt/ai-lab/
├── compose.yaml          # 编排（容器名 ai-lab-api / ai-lab-web）
├── api.env               # 生产环境变量（含密码与 JWT 密钥，权限 600，勿提交仓库）
├── backend/              # 后端源码 + Dockerfile + requirements.txt（构建上下文）
├── web/
│   ├── dist/             # 前端构建产物
│   ├── nginx.conf        # 站点配置
│   └── proxy-common.inc  # 反代公共参数（SSE 不缓冲、1800s 超时、32m 上传上限）
└── data/
    ├── uploads/          # 头像等公开文件（对应数据库里的 /uploads/xxx）
    ├── storage/          # 知识库原始文档与解析产物
    └── logs/             # 按日期归档的应用日志
```

## 常用命令

```bash
cd /opt/ai-lab

docker compose ps                       # 状态（api 应为 healthy）
docker compose logs -f api              # 后端日志
docker logs ai-lab-web --tail 50        # nginx 访问日志
docker compose restart api              # 只重启后端
docker compose down && docker compose up -d   # 整体重启（数据在卷里，不受影响）
```

## 更新代码

在本机执行：

```powershell
.\deploy\redeploy.ps1                 # 前后端都更新
.\deploy\redeploy.ps1 -SkipFrontend   # 只改后端
```

脚本流程：本地 `npm run build` → 打包 → 上传 `/tmp/ai-lab-deploy` → 服务器替换
`backend/` 与 `web/dist/` → `docker compose build api` → `up -d` → 健康检查。

仅调 nginx 配置时，不必重建镜像：

```bash
scp deploy/nginx.conf aliyun:/opt/ai-lab/web/nginx.conf
ssh aliyun "docker exec ai-lab-web nginx -t && docker exec ai-lab-web nginx -s reload"
```

## 必须守住的约束

1. **`api.env` 里的 `JWT_SECRET_KEY` 不能改。** 未配置 `AI_CONFIG_ENCRYPTION_KEY` 时，
   数据库中 AI 供应商的 API Key 就是用 JWT 密钥加密的；一改，那些 Key 全部无法解密。
   同理，改了它所有已登录用户的 token 立即失效。
2. **`DB_HOST` 必须是 `ai-postgres`。** 容器通过 `ai-postgres-net` 直达数据库，
   不要写公网 IP，否则绕公网还依赖 5432 的安全组。
3. 数据库**不重建**。`ai-lab-api` 只是接入已有网络，`docker compose down` 不会影响
   `ai-postgres` 的数据；但仍建议定期 `pg_dump`。
4. `MAX_REQUEST_BODY_BYTES`（后端 22 MiB）必须小于 nginx `client_max_body_size`（32m），
   改大上传限制时两处一起改。

## 待办 / 风险

- **5432 端口对公网开放**（`0.0.0.0:5432`），这是当前最大的暴露面，建议在阿里云安全组
  收紧到固定 IP，或改为只走容器内网（本项目部署后已不需要公网 5432）。
- 目前只有 HTTP。要上域名与 HTTPS，需要安全组放行 443 并配置证书，可在 `web/nginx.conf`
  增加 443 server 段，并把 80 跳转到 443。
- 服务器 2 核 1.6 GB 内存。当前占用约 800 MB（api 175 MB + pg 70 MB 等），够用；
  若再并行跑前端构建或其它服务容易触发 OOM。
- 前端产物 `index-*.js` 约 838 kB（gzip 265 kB），后续可用动态 import 拆包优化首屏。
- **磁盘性能是本机瓶颈**：40 GB ESSD 在突发读扫描时实测被压到约 2500 IOPS / 单次读 64 ms，
  `wa` 冲到 96%，所有进程连带卡死。若长期需要稳定响应，建议升级到 PL1 及以上（IOPS 提升一个量级）。

## 故障记录

### 2026-10-21 前端提示"连接不上数据库"

现象：页面报数据库错误；`/health/ready` 时而 200 时而超时；容器被标记 unhealthy。

根因链（不是代码或数据库问题）：

1. 机器上有进程在**持续全盘读**（实测 180–200 MB/s、约 2500 次/s 的小块读、单次读延迟 64 ms），
   把 40 GB ESSD 打到性能上限，`wa` 96%，大量进程卡在 D 状态（`docker ps` 也要几十秒）。
2. dockerd 在这种状态下无法及时应答**容器内嵌 DNS**，`ai-postgres` 解析超时（`EAI_AGAIN`），
   SQLAlchemy 连接失败 → 前端看到"连不上数据库"。日志里共记录 72 次该错误。
3. 处置期间重建 api 容器，IP 从 `10.210.2.2` 变成新地址，而 nginx 启动时只解析一次 upstream，
   缓存了旧 IP → 出现 `502 Bad Gateway`。

已做的加固（都是永久性的）：

- api → postgres 改为 `/etc/hosts`（`extra_hosts`），不再依赖 dockerd DNS；
- nginx → api 改为**固定 IP**（`10.211.0.10`），api 重建后不再 502；
- 健康检查超时放宽（10 s / 5 次），避免繁忙时误报 unhealthy；
- 停掉了 `dpanel-plugin-monitor`（`dpanel/explorer` 文件浏览插件）并取消其自动重启，
  实测停掉后读盘明显下降。需要时 `docker update --restart=always dpanel-plugin-monitor &&
  docker start dpanel-plugin-monitor` 可恢复。

遗留观察：突发读仍会出现（约 50–100 MB/s，`wa` 低，不影响响应），主要来自 dpanel、服务器上
常驻的 `codex app-server` 等非业务进程。若再次出现卡顿，先按上文顺序逐个停非业务容器/进程定位。

**教训**：`docker compose up -d` 只改 api 时，web 不会跟着重建；已通过固定 IP 消除这一隐患，
以后改 `api.ipv4_address` 记得同步 `nginx.conf`。
