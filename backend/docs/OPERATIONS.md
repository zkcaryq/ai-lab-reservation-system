# 后端开发与运维命令

## 依赖和启动

```powershell
uv sync
uv run python -m app --reload
```

生产环境设置 `APP_ENV=production`，并且不使用 `--reload`。生产环境关闭 Swagger 和 OpenAPI JSON。

## Alembic

```powershell
uv run alembic current
uv run alembic history
uv run alembic check
uv run alembic revision --autogenerate -m "迁移说明"
uv run alembic upgrade head
uv run alembic downgrade -1
```

本地不填写 `MIGRATION_DB_USER` 和 `MIGRATION_DB_PASSWORD` 时，Alembic 使用运行账号。生产环境需要 DDL 权限隔离时再同时配置这两个字段。

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

- live 不访问数据库。
- ready 使用注入的 AsyncSession 执行 `SELECT 1`。

## 查看日志

日志同时输出到终端和按启动时间创建的独立文件，日期和时间使用 UTC：

```text
logs/2026-10-06/app-13-45-20Z-pid-12345.log
```

每个进程启动时创建新文件；`--reload`重新启动工作进程时也会创建新文件。查看最新文件：

```powershell
$latestLog = Get-ChildItem .\logs -Recurse -File -Filter "app-*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
Get-Content -LiteralPath $latestLog.FullName -Tail 100
Select-String -LiteralPath $latestLog.FullName -Pattern "error_id"
Select-String -LiteralPath $latestLog.FullName -Pattern "request_id"
```

跨全部历史文件查找：

```powershell
Select-String -Path .\logs\*\app-*.log* -Pattern "error_id"
```

单个启动日志达到 5 MiB 后轮转，最多保留 5 份该文件的历史分片。按启动分文件会持续占用
磁盘，应用不会自动删除历史记录；生产环境应由运维平台配置保留周期。

## 静态检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall app alembic
```
