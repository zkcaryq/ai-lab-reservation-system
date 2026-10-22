# AI 智能实验室预约系统 · 后端镜像
# 依赖清单由 `uv export --no-dev --no-emit-project --no-hashes` 生成，
# 与 pyproject.toml / uv.lock 保持一致，镜像内不需要 uv。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先只装依赖，源码改动时可以复用这一层缓存。
COPY requirements.txt ./
RUN pip install --no-cache-dir \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -r requirements.txt

COPY . .

# 不写入 .pyc；uploads 与 storage 通过卷挂载，不打进镜像。
RUN mkdir -p /app/uploads /app/storage/knowledge

EXPOSE 8000

# 探活只看进程，不依赖数据库，避免数据库抖动导致容器被反复重启。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"]

# --no-access-log 与 app/__main__.py 保持一致；--proxy-headers 让 request.client 拿到真实访客 IP。
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--no-access-log"]
