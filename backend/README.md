# AI 智能实验室预约系统后端

基于 FastAPI、SQLAlchemy 2 AsyncIO、PostgreSQL、psycopg 3 和 Alembic 的异步后端。

## 当前业务

- User ORM 与 Alembic 迁移
- `POST /api/auth/login`
- `GET /health/live`
- `GET /health/ready`

登录功能当前严格跟随学习教程，暂时比较明文密码；密码哈希和 JWT 将在后续教程对应章节加入。

## 启动

```powershell
uv sync
uv run alembic upgrade head
uv run python -m app --reload
```

Swagger：`http://127.0.0.1:8000/docs`

## 分层

```text
Router -> Service -> AsyncSession -> ORM -> PostgreSQL
```

- Router 负责 HTTP 输入输出和 Session 依赖声明。
- Service 负责查询及业务判断，不依赖 FastAPI。
- `get_db_session()` 为每个请求创建并关闭独立 AsyncSession。
- 应用启动不自动建库、建 Schema、建表或执行迁移。

详细说明见 [架构说明](docs/ARCHITECTURE.md) 和 [开发运维命令](docs/OPERATIONS.md)。

## 静态验证

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall app alembic
uv run alembic check
```

本项目按当前学习需求不包含 pytest 和 tests 目录。
