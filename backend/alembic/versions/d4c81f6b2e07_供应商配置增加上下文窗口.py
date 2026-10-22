"""供应商配置增加上下文窗口

Revision ID: d4c81f6b2e07
Revises: b7e2c41a9f03
Create Date: 2026-10-20 17:24:00.000000

前端聊天页用"当前模型的上下文窗口"当进度条分母。窗口原本只写在代码里的
MODEL_CATALOG，管理员换成目录外的模型（例如给轻量对话配一个便宜模型）就查不到，
进度条直接消失。这里把窗口存进配置行，由配置页在选模型时一并带上。

可为空：老配置和"手填模型名"的情况仍然回退到 MODEL_CATALOG。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4c81f6b2e07'
down_revision: str | Sequence[str] | None = 'b7e2c41a9f03'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'ai_provider_configs',
        sa.Column(
            'context_window',
            sa.Integer(),
            nullable=True,
            comment='模型上下文窗口token数；空则查MODEL_CATALOG',
        ),
        schema='app',
    )


def downgrade() -> None:
    op.drop_column('ai_provider_configs', 'context_window', schema='app')
