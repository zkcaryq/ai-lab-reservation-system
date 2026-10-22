"""供应商配置增加生成参数与系统提示词

Revision ID: b7e2c41a9f03
Revises: e2227d0a500f
Create Date: 2026-10-20 17:16:00.000000

给每个能力配置增加四个管理员可调项：
- temperature / top_p：采样参数，空表示用供应商默认值；
- max_output_tokens：单次输出上限，空表示用代码里的全局上限；
- system_prompt：自定义系统提示词，空表示用代码内置提示词。

这四项都允许为空，所以升级后现有 5 个能力的配置行为完全不变。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e2c41a9f03'
down_revision: str | Sequence[str] | None = 'e2227d0a500f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'ai_provider_configs',
        sa.Column('temperature', sa.Float(), nullable=True, comment='采样温度0-2；空则用供应商默认'),
        schema='app',
    )
    op.add_column(
        'ai_provider_configs',
        sa.Column('top_p', sa.Float(), nullable=True, comment='核采样0-1；空则用供应商默认'),
        schema='app',
    )
    op.add_column(
        'ai_provider_configs',
        sa.Column('max_output_tokens', sa.Integer(), nullable=True, comment='单次输出token上限；空则用全局默认'),
        schema='app',
    )
    op.add_column(
        'ai_provider_configs',
        sa.Column('system_prompt', sa.Text(), nullable=True, comment='自定义系统提示词；空则用内置提示词'),
        schema='app',
    )


def downgrade() -> None:
    op.drop_column('ai_provider_configs', 'system_prompt', schema='app')
    op.drop_column('ai_provider_configs', 'max_output_tokens', schema='app')
    op.drop_column('ai_provider_configs', 'top_p', schema='app')
    op.drop_column('ai_provider_configs', 'temperature', schema='app')
