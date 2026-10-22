"""把用户问题向量化，并从pgvector检索可用于回答的知识Chunk。

[链路定位] RAG 检索链路的编排入口（与入库链路完全独立，属于用户提问这一次请求）：

    上游：chat_pipeline_services.prepare_text_chat_context() / ai_router.chat_with_image()
          调用 search_knowledge()
    下游：bailian_embedding_services.create_fused_embedding()  —— 把问题变成 1024 维向量
          build_candidate_rows()  —— 向量召回 + 字面(ILIKE)召回，RRF 融合
          bailian_rerank_services.rerank_documents_with_scores()  —— 二次精排（可选）
    产出：list[RetrievedChunk]，交给 ai_services._build_rag_input() 拼成【知识库参考资料】。
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import and_, case, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.knowledge_models import KnowledgeChunk, KnowledgeDocument
from app.services.knowledge.bailian_embedding_services import create_fused_embedding
from app.services.knowledge.bailian_rerank_services import rerank_documents_with_scores
from app.services.knowledge.knowledge_storage_services import resolve_storage_key

settings = get_settings()
logger = logging.getLogger(__name__)

# RRF只比较同一次检索中的名次，不依赖向量距离与关键词分数使用相同量纲。
RRF_RANK_CONSTANT = 60

# 百炼明确说明relevance_score主要用于同一次请求内比较，不能跨请求当绝对置信度。
# 因此这里保留“达到本次最高分60%”的候选，而不是写死一个全局绝对阈值。
RERANK_RELATIVE_SCORE_RATIO = 0.60

# rerank 的分数经常挤在 0.80—0.88 之间（不同文档差不到 0.05），按条数截断会把
# 真正关键、但“语义不像问答”的记录（比如培训台账的一行表格）挤到第 6 名。
# 这里比最终条数多要 2 条，给后面“融合排名第一必须保留”的兜底留出空间。
RERANK_EXTRA_CANDIDATES = 1

# 复杂问题最多拆出3个检索重点，加上完整问题一共不超过4路召回。候选融合后只把
# 前60条交给Rerank，防止长文档库无限放大排序输入和响应时间。
MAX_FOCUS_QUERIES = 3
RERANK_CANDIDATE_LIMIT = 60
SUBJECT_SEPARATOR_PATTERN = re.compile(r"(?<!\d)[：:](?!\d)")
FOCUS_SPLIT_PATTERN = re.compile(r"(?<!\d)[：:](?!\d)|[，,、；;。！？?\n]+")

# 相邻块只补少量边界文字，主命中块保持完整。既能补回条件/结论，又不会让5个来源
# 膨胀成几十KB上下文。
NEIGHBOR_CONTEXT_CHARS = 600

QUERY_FILLER_WORDS = (
    # 问句虚词
    "请问",
    "哪些",
    "怎么",
    "如何",
    "什么",
    "为什么",
    "是否",
    "能不能",
    "可以",
    "需要",
    "一下",
    "分别",
    "说明",
    "相关",
    "有关",
    # 句子连接词/助词：切成独立片段，避免跨词边界的“昊说/说他/他焊”噪声
    "他说",
    "她说",
    "说他",
    "说她",
    "已经",
    "通过",
    "还能",
    "还要",
    "以及",
    "然后",
    "现在",
    "想要",
    "打算",
    "计划",
    "就能",
    "用来",
    "也能",
    "并且",
)
GENERIC_BIGRAMS = {
    "实验",
    "验室",
    "使用",
    "需要",
    "哪些",
    "怎么",
    "如何",
    "什么",
    # 下面这些是由“他说/已经/还能…”等连接、助词产生的二元组，本身没有检索价值。
    # 过滤后能把每次词法补召回的 OR 条件从十几个降到几个，降低全表扫的宽度。
    "他说",
    "她说",
    "已经",
    "通过",
    "过了",
    "还能",
    "还要",
    "以及",
    "然后",
    "现在",
    "想要",
    "打算",
    "计划",
    "就能",
    "用来",
    "也能",
    "并且",
    # 跨词边界的碎二元组，纯噪声
    "昊说",
    "他焊",
    "接安",
    "试已",
}

# 词法补召回最多保留多少词。补召回是向量召回的辅助，宁缺毋滥；
# 上限同时限制了单个查询里 OR 条件的数量，避免长问题放大扫描。
MAX_LEXICAL_TERMS = 12


def _escape_ilike(value: str) -> str:
    """转义 ILIKE 通配符，确保检索词按字面含义参与补召回。"""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def extract_lexical_terms(query: str) -> list[str]:
    """生成字面补召回词；最终相关性仍由 rerank 判断。

    只挑“专指”的词：编号/型号/缩写（含字母）和内容词二元组。
    纯数字（时间、容量、数量）不做补召回——它们在几百个 chunk 里都命中，
    只会稀释稀有词（人名/工单号）的权重。
    """

    terms: list[str] = []

    def add(value: str) -> None:
        """去重加入长度合格的词法候选，并保持首次出现顺序。"""

        value = value.strip()
        if len(value) >= 2 and value not in terms:
            terms.append(value)

    # ASCII：带字母才算（FX-2026-044 / 3D / LoRa / GPU），"19""30""42"这类纯数字跳过。
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,}", query):
        if re.search(r"[A-Za-z]", token):
            add(token)

    for chinese in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        # 用空格替换连接词再切段：段内再滑二元组，就不会出现“赵文昊说”被切成
        # “文昊/昊说/说他”这种跨词边界的噪声；同时保住“赵文昊”这个完整词。
        cleaned = chinese
        for filler in QUERY_FILLER_WORDS:
            cleaned = cleaned.replace(filler, " ")
        for segment in cleaned.split():
            segment = segment.strip()
            if 2 <= len(segment) <= 12:
                add(segment)
            for index in range(max(0, len(segment) - 1)):
                bigram = segment[index : index + 2]
                if bigram not in GENERIC_BIGRAMS:
                    add(bigram)
        if len(terms) >= MAX_LEXICAL_TERMS:
            break
    return terms[:MAX_LEXICAL_TERMS]


def build_focus_queries(question: str) -> list[str]:
    """从复杂问题中提取少量检索重点；保留完整原问题作为每个重点的语境。"""

    normalized = question.strip()
    if not normalized:
        return []

    # 冒号前通常是共同主题，例如“请还原3D打印机故障时间线：……”。把它带到
    # 每个子问题中，避免“具体故障是什么”脱离3D打印机后召回其他设备。
    subject = ""
    subject_match = SUBJECT_SEPARATOR_PATTERN.search(normalized)
    if subject_match is not None:
        subject = normalized[: subject_match.start()].strip()

    parts = [
        part.strip(" ：:")
        for part in FOCUS_SPLIT_PATTERN.split(normalized)
        if len(part.strip(" ：:")) >= 4
    ]
    # 只有一个语义片段时，完整问题本身就是最好的检索词，不重复调用Embedding。
    if len(parts) < 2:
        return []

    candidates: list[str] = []
    for part in parts:
        # 冒号前的共同主题已经包含在完整问题中，把有限的子查询名额留给具体问题。
        if part == subject:
            continue
        focus = f"{subject}：{part}" if subject and subject not in part else part
        if focus not in candidates:
            candidates.append(focus)
        if len(candidates) >= MAX_FOCUS_QUERIES:
            break
    return candidates


def fuse_candidate_groups(candidate_groups: list[list[Any]]) -> list[Any]:
    """用RRF合并完整问题与多个检索重点的候选排名。"""

    rows_by_chunk_id: dict[int, Any] = {}
    scores: dict[int, float] = {}
    for rows in candidate_groups:
        for rank, row in enumerate(rows, start=1):
            chunk_id = row[0].id
            rows_by_chunk_id.setdefault(chunk_id, row)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_RANK_CONSTANT + rank)
    ranked_ids = sorted(rows_by_chunk_id, key=scores.__getitem__, reverse=True)
    return [rows_by_chunk_id[chunk_id] for chunk_id in ranked_ids[:RERANK_CANDIDATE_LIMIT]]


def _neighbor_matches(main: KnowledgeChunk, neighbor: KnowledgeChunk) -> bool:
    """判断相邻序号是否仍属于同一自然上下文，阻止跨章节盲目拼接。"""

    if main.heading_path:
        return neighbor.heading_path == main.heading_path
    if main.page_number is not None:
        return neighbor.page_number == main.page_number
    if main.sheet_name:
        return neighbor.sheet_name == main.sheet_name
    return False


async def build_expanded_contents(
    session: AsyncSession,
    *,
    rows: list[Any],
) -> dict[int, str]:
    """为最终命中块补充同章节/同页的直接邻居，返回chunk_id到上下文的映射。"""

    text_chunks = [row[0] for row in rows if row[0].modality == "text"]
    if not text_chunks:
        return {}

    conditions = [
        and_(
            KnowledgeChunk.document_id == chunk.document_id,
            KnowledgeChunk.chunk_index.in_([max(0, chunk.chunk_index - 1), chunk.chunk_index + 1]),
        )
        for chunk in text_chunks
    ]
    neighbors = list((await session.scalars(select(KnowledgeChunk).where(or_(*conditions)))).all())

    expanded: dict[int, str] = {}
    for main in text_chunks:
        before = next(
            (
                item
                for item in neighbors
                if item.document_id == main.document_id
                and item.chunk_index == main.chunk_index - 1
                and _neighbor_matches(main, item)
            ),
            None,
        )
        after = next(
            (
                item
                for item in neighbors
                if item.document_id == main.document_id
                and item.chunk_index == main.chunk_index + 1
                and _neighbor_matches(main, item)
            ),
            None,
        )

        parts: list[str] = []
        if before is not None:
            parts.append(f"【紧邻上文】\n{before.content[-NEIGHBOR_CONTEXT_CHARS:]}")
        parts.append(f"【本次命中】\n{main.content}")
        if after is not None:
            parts.append(f"【紧邻下文】\n{after.content[:NEIGHBOR_CONTEXT_CHARS]}")
        if before is not None or after is not None:
            expanded[main.id] = "\n\n".join(parts)
    return expanded


@dataclass(slots=True)
class RetrievedChunk:
    """内部检索结果；供AI Service构造上下文，不直接作为HTTP响应。"""

    # 命中的Chunk主键，主要用于日志和后续评测，不直接暴露全文查询接口。
    chunk_id: int

    # 来源文档ID和文件名用于构造回答来源引用。
    document_id: int
    file_name: str

    # content是交给聊天模型的真实知识正文。
    content: str

    # 页码和标题帮助模型、前端定位原文；没有时保持None。
    page_number: int | None
    heading_path: str | None

    # 图片Chunk保留模态和私有存储键；HTTP层只暴露受鉴权的图片读取地址。
    modality: str
    image_storage_key: str | None

    # 余弦距离越小越相似，它不是正确率，也不是模型置信度。
    distance: float


def build_rerank_document(
    chunk: KnowledgeChunk,
    *,
    file_name: str,
) -> str:
    """把来源信息与正文组合成Rerank输入，避免短Chunk丢失文档主题。"""

    parts = [f"来源文档：{file_name}"]
    if chunk.heading_path:
        parts.append(f"章节：{chunk.heading_path}")
    parts.append(f"正文：{chunk.content}")
    return "\n".join(parts)


async def get_source_image_path(
    session: AsyncSession,
    *,
    chunk_id: int,
) -> Path | None:
    """返回可用图片Chunk的私有文件路径；不存在、停用或缺文件时返回None。"""

    statement = (
        select(KnowledgeChunk.image_storage_key)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeChunk.id == chunk_id,
            KnowledgeChunk.image_storage_key.is_not(None),
            KnowledgeDocument.status == "completed",
            KnowledgeDocument.enabled.is_(True),
        )
    )
    storage_key = await session.scalar(statement)
    if storage_key is None:
        return None

    path = resolve_storage_key(storage_key)
    return path if path.is_file() else None


async def build_candidate_rows(
    session: AsyncSession,
    *,
    query: str,
    query_embedding: list[float],
    candidate_limit: int,
) -> list[Any]:
    """构建向量 + 字面补召回候选池，供生产检索和A/B评测共用。

    面试口径：这里不是拿一个阈值做“是否相似”的二分类，而是先按余弦距离
    从小到大取 Top N。pgvector 的余弦距离等于 ``1 - cosine_similarity``：

    ``cosine_similarity = (q·d) / (||q|| * ||d||)``

    SQLAlchemy 的 ``cosine_distance()`` 会编译为 pgvector 的 ``<=>`` 运算符；
    数据库中的 HNSW ``vector_cosine_ops`` 索引正是为
    ``ORDER BY embedding <=> query_vector LIMIT N`` 这种近邻查询准备的。
    距离越小只表示向量空间更接近，不表示答案正确率或模型置信度。
    """

    # 这一行只是构造SQL表达式，没有在Python里遍历所有Chunk计算余弦。
    # 真正计算发生在PostgreSQL；当表有数据且查询规划器判断值得使用时，
    # HNSW会用近似最近邻搜索减少候选访问。小表时规划器仍可能选择顺序扫描，
    # 是否实际命中索引必须看该数据库上的EXPLAIN，不能仅凭“建过索引”下结论。
    distance_expression = KnowledgeChunk.embedding.cosine_distance(query_embedding).label(
        "distance"
    )
    common_filters = (
        KnowledgeDocument.status == "completed",
        KnowledgeDocument.enabled.is_(True),
    )
    vector_statement = (
        select(KnowledgeChunk, KnowledgeDocument.original_name, distance_expression)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(*common_filters)
        .order_by(distance_expression)
        .limit(candidate_limit)
    )
    vector_rows = (await session.execute(vector_statement)).all()

    lexical_rows: list[Any] = []
    terms = extract_lexical_terms(query)
    if terms:
        # 词法通道不是PostgreSQL全文检索，也没有使用倒排词典/中文分词器；
        # 它是“提取少量专指词 + ILIKE任意位置子串匹配”的补召回。
        # 迁移9b3f7c2d1a04为content和original_name建立了pg_trgm GIN索引，
        # 普通B-tree无法有效支持'%term%'。heading_path目前没有trigram索引，
        # 而三列又通过OR连接，所以整个复合SQL是否走GIN仍由规划器按数据量、
        # 选择率和连接顺序决定；要用EXPLAIN验证，不能宣称永远没有全表扫描。
        conditions = []
        score_parts = []
        for term in terms:
            pattern = f"%{_escape_ilike(term)}%"
            condition = or_(
                KnowledgeChunk.content.ilike(pattern, escape="\\"),
                KnowledgeChunk.heading_path.ilike(pattern, escape="\\"),
                KnowledgeDocument.original_name.ilike(pattern, escape="\\"),
            )
            conditions.append(condition)
            score_parts.append(case((condition, 1), else_=0))
        lexical_score = sum(score_parts, start=literal(0))
        lexical_statement = (
            select(KnowledgeChunk, KnowledgeDocument.original_name, distance_expression)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(*common_filters, or_(*conditions))
            .order_by(lexical_score.desc(), distance_expression)
            .limit(candidate_limit)
        )
        lexical_rows = list((await session.execute(lexical_statement)).all())

    # 向量距离与关键词命中数不在同一量纲，不能直接相加。RRF按两份结果中的
    # 排名累加分数：同一Chunk在两路都靠前时会自然升高，同时不会让某一路垄断。
    rows_by_chunk_id: dict[int, Any] = {}
    rrf_scores: dict[int, float] = {}
    for ranked_rows in (vector_rows, lexical_rows):
        for rank, row in enumerate(ranked_rows, start=1):
            chunk_id = row[0].id
            rows_by_chunk_id.setdefault(chunk_id, row)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (RRF_RANK_CONSTANT + rank)

    ranked_chunk_ids = sorted(
        rows_by_chunk_id,
        key=lambda chunk_id: rrf_scores[chunk_id],
        reverse=True,
    )
    return [rows_by_chunk_id[chunk_id] for chunk_id in ranked_chunk_ids]


async def search_knowledge(
    session: AsyncSession,
    *,
    query: str,
    focus_question: str | None = None,
    query_image_path: Path | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """融合向量召回、精确短语补召回和可选Rerank，返回最终Top K。"""

    candidate_limit = max(limit, settings.RAG_CANDIDATE_LIMIT)
    retrieval_queries = [query]
    if query_image_path is None:
        # 图片查询只生成一次图文融合向量；文本复杂问题才追加多个检索重点。
        for focus in build_focus_queries(focus_question or query):
            focused_query = f"{query}\n【检索重点】\n{focus}"
            if focused_query not in retrieval_queries:
                retrieval_queries.append(focused_query)

    candidate_groups: list[list[Any]] = []
    for retrieval_query in retrieval_queries:
        # 每个检索重点都调用与入库一致的融合向量模型；多路召回解决一个长问题中
        # 多个条件被单个向量平均的问题。当前顺序调用可避免瞬时并发触发供应商限流。
        query_embedding = await create_fused_embedding(
            text=retrieval_query,
            image_path=query_image_path,
        )
        candidate_groups.append(
            await build_candidate_rows(
                session,
                query=retrieval_query,
                query_embedding=query_embedding,
                candidate_limit=candidate_limit,
            )
        )
    candidate_rows = fuse_candidate_groups(candidate_groups)
    logger.info(
        "rag candidates built query_count=%d candidate_count=%d",
        len(retrieval_queries),
        len(candidate_rows),
    )

    rerank_results = await rerank_documents_with_scores(
        query=query,
        # 分块后正文可能只包含“校准步骤”等局部内容，不再重复设备名称。
        # 把文件名和章节一并交给排序模型，才能区分相似设备手册中的短片段。
        documents=[build_rerank_document(row[0], file_name=row[1]) for row in candidate_rows],
        # 多要 2 条，避免“按条数截断”正好切掉融合排名第一的关键记录。
        top_n=min(len(candidate_rows), limit + RERANK_EXTRA_CANDIDATES),
    )
    if rerank_results is None:
        # 排序服务未配置或暂时故障时，使用已经过RRF融合的候选顺序保证接口可用。
        rows = candidate_rows[:limit]
    elif not rerank_results:
        rows = []
    else:
        # 不再无条件塞满Top5。尾部结果若明显低于本次最高分，大概率只是“候选中
        # 相对没那么差”，并不适合作为回答依据或文档引用。
        score_cutoff = rerank_results[0].relevance_score * RERANK_RELATIVE_SCORE_RATIO
        rows = [
            candidate_rows[result.index]
            for result in rerank_results
            if result.relevance_score >= score_cutoff
        ][: limit + RERANK_EXTRA_CANDIDATES]

        # 兜底：向量 + 字面两路融合后的第 1 名，如果没被 rerank 选中，补进来。
        # 典型场景：问“赵文昊能去吗”，培训台账那一行在候选里排第 1，但 rerank
        # 觉得它“不像回答”，把它压到第 6 名——补回来后模型才能看到 58 分未通过。
        selected_ids = {row[0].id for row in rows}
        if candidate_rows and candidate_rows[0][0].id not in selected_ids:
            rows.append(candidate_rows[0])
            logger.info(
                "rag kept top fused candidate that rerank skipped chunk_id=%s doc=%s",
                candidate_rows[0][0].id,
                candidate_rows[0][1],
            )

    expanded_contents = await build_expanded_contents(session, rows=rows)
    logger.info(
        "rag evidence selected selected_count=%d expanded_count=%d rerank_available=%s",
        len(rows),
        len(expanded_contents),
        rerank_results is not None,
    )

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            file_name=file_name,
            content=expanded_contents.get(chunk.id, chunk.content),
            page_number=chunk.page_number,
            heading_path=chunk.heading_path,
            modality=chunk.modality,
            image_storage_key=chunk.image_storage_key,
            distance=float(distance),
        )
        for chunk, file_name, distance in rows
    ]
