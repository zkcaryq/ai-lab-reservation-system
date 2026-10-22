# Service 层目录说明

按**领域**分包，每个包内自洽；文件名统一保持 `xxx_services.py` 后缀，方便和 `xxx_router.py` /
`xxx_models.py` / `xxx_schemas.py` 对应。

| 包 | 放什么 |
|---|---|
| `auth/` | 登录、注册、用户资料、管理员用户管理 |
| `lab/` | 实验室信息、设备台账 |
| `reservation/` | 预约创建、取消、审核、后台自动审核扫描 |
| `knowledge/` | 知识文档增删查、解析、入库、检索、私有存储、后台 Worker |
| `ai/` | 对话、Agent 工具循环、待确认预约动作、供应商配置、用量统计、`providers/` 适配器 |

## 两条硬规则

**1. `__init__.py` 必须是空的（最多一行 docstring），禁止 re-export。**

`ai/` 和 `knowledge/` 之间存在包级双向依赖：

- `ai/ai_services.py` 需要 `knowledge.knowledge_retrieval_services` 做检索；
- `knowledge/knowledge_ingestion_services.py` 需要 `ai.ai_provider_services` 读模型配置。

模块级没有循环，所以现在能正常导入。但一旦某个 `__init__.py` 写了
`from .ai_services import ...`，导入任意子模块都会触发整条依赖链，立刻变成真循环。

**2. 新功能加到对应领域包，不要新建顶层 `*_services.py`。**

判断方法：这个功能主要操作哪张表/哪个领域。

- 预约相关 → `reservation/`
- 知识文档或检索相关 → `knowledge/`
- 模型调用、对话、供应商 → `ai/`

## 常见导入写法

```python
from app.services.reservation import reservation_services
from app.services.ai import ai_services, ai_provider_services
from app.services.knowledge import knowledge_retrieval_services
```

同包内的模块互相引用时，可以写成包内相对路径（`from app.services.ai import chat_services`），
保持全项目统一即可。
