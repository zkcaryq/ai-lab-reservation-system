"""供应商配置增加dashscope地址字段

Revision ID: b1d2a3c4e5f6
Revises: 2c3595c851fe
Create Date: 2026-10-20 11:30:00.000000

新增 ``dashscope_base_url`` 列：用于百炼 embedding/rerank/list_models 这类走
``/api/v1`` 根地址的能力，与聊天 ``/compatible-mode/v1`` 的 ``base_url``
分离。可为空：为空时由代码从 ``base_url`` 派生 ``/api/v1``，保留旧数据兼容。

同时把 ``base_url`` 的列注释由旧版 ``/v1`` 更新为 ``/compatible-mode/v1``，
反映新的"聊天端点写/compatible-mode/v1"约定。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b1d2a3c4e5f6'
down_revision: str | Sequence[str] | None = '2c3595c851fe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'ai_provider_configs',
        sa.Column(
            'dashscope_base_url',
            sa.String(length=300),
            nullable=True,
            comment=(
                '百炼DashScope /api/v1 根地址；空则由 base_url 派生'
            ),
        ),
        schema='app',
    )
    # 同步调整 base_url 列注释；只动 comment 不动类型/可空性。
    op.alter_column(
        'ai_provider_configs',
        'base_url',
        existing_comment='OpenAI兼容端点，只写到/v1',
        comment='OpenAI兼容端点(聊天/视觉)，写到/compatible-mode/v1',
        schema='app',
    )


def downgrade() -> None:
    op.alter_column(
        'ai_provider_configs',
        'base_url',
        existing_comment='OpenAI兼容端点(聊天/视觉)，写到/compatible-mode/v1',
        comment='OpenAI兼容端点，只写到/v1',
        schema='app',
    )
    op.drop_column('ai_provider_configs', 'dashscope_base_url', schema='app')