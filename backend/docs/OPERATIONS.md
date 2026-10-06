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

```powershell
Get-Content .\logs\app.log -Tail 100
Select-String -Path .\logs\app.log -Pattern "error_id"
Select-String -Path .\logs\app.log -Pattern "request_id"
```

日志同时输出到终端和 `logs/app.log`。文件达到 5 MiB 后轮转，保留 5 份历史文件。

## 静态检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall app alembic
```
