"""知识库增加 trigram 索引（加速 ILIKE 前导通配）

Revision ID: 9b3f7c2d1a04
Revises: d4c81f6b2e07
Create Date: 2026-10-21 10:20:00.000000

词法补召回用 ``content ILIKE '%term%'``、``original_name ILIKE '%term%'`` 做前导
通配，btree 用不上，数据量大了会退化成全表扫。pg_trgm 的 GIN 索引能加速这种
任意位置子串匹配。

注意：本迁移只建索引；pg_trgm 扩展必须先在库里装好（``CREATE EXTENSION IF NOT
EXISTS pg_trgm``，需要超级用户执行一次），否则 ``gin_trgm_ops`` 类型不存在会报错。
"""
from collections.abc import Sequence

from alembic import op

revision: str = '9b3f7c2d1a04'
down_revision: str | Sequence[str] | None = 'd4c81f6b2e07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_content_trgm "
        "ON app.knowledge_chunks USING gin (content gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_original_name_trgm "
        "ON app.knowledge_documents USING gin (original_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.ix_knowledge_chunks_content_trgm")
    op.execute("DROP INDEX IF EXISTS app.ix_knowledge_documents_original_name_trgm")
