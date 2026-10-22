# 反代公共参数：被 nginx.conf 的 /api /uploads /health 复用。
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";

# AI 对话走 SSE（text/event-stream），关掉缓冲才能逐字吐字。
# 上传也一样：请求体不落盘缓冲，直接透传给后端。
proxy_buffering off;
proxy_request_buffering off;
proxy_cache off;

# 知识库入库与长回答耗时较长，给足超时。
proxy_connect_timeout 10s;
proxy_read_timeout 1800s;
proxy_send_timeout 1800s;
