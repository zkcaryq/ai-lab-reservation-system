"""AI 聊天接口的轻量限流：只挡“单位时间内请求过密”，不做预算/计费。

为什么放在内存里：本项目明确单进程 uvicorn（部署文档禁止 --workers），
进程内一个字典就能覆盖全部请求。代价是重启后计数清零、多进程时各算各的——
这是“防手滑/防脚本暴力刷”的闸门，不是精确计费，够用即可。

被限流的范围：只有会触发外部付费调用的三个聊天入口（/chat、/chat/stream、
/chat/image）。意图、检索、模型调用都在这些入口内部发生。
"""

import time
from collections import defaultdict, deque

# 默认策略：每个用户每 60 秒最多 N 次。可按实际并发调。
MAX_REQUESTS_PER_WINDOW = 10
WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """按 key 记录时间戳的滑窗限流器。key 用 user_id。"""

    def __init__(
        self,
        max_requests: int = MAX_REQUESTS_PER_WINDOW,
        window_seconds: float = WINDOW_SECONDS,
    ) -> None:
        """初始化窗口大小、请求上限和按用户保存的时间戳队列。"""

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, key: int) -> bool:
        """本窗口内是否还放行；放行则记录本次时间。"""

        now = time.monotonic()
        queue = self._hits[key]

        # 丢掉窗口之外的历史时间戳，避免队列无限增长。
        while queue and now - queue[0] >= self.window_seconds:
            queue.popleft()

        if len(queue) >= self.max_requests:
            return False

        queue.append(now)
        return True

    def reset(self, key: int) -> None:
        """清掉某个 key 的计数（测试或管理员解封用）。"""

        self._hits.pop(key, None)


# 模块级单例：整个进程共享同一份计数。
rate_limiter = SlidingWindowRateLimiter()
