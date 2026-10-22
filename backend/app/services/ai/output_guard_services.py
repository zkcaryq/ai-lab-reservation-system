"""模型输出护栏：清洗供应商特殊 token，识别“工具调用被写进正文”。

为什么需要这个模块：
MiniMax 的 Responses 接口在“模型想调工具、但这一轮拿不到工具（或已被禁止调工具）”
时，会把工具调用原样写进正文，形如::

    ]<]minimax[>[<tool_call>]<]minimax[>[<invoke name="list_lab_equipments">]...

这些 `]<]minimax[>[` 是模型内部的特殊 token，不是给用户看的内容。一旦原样落库，
聊天记录和界面里就只剩一坨乱码（第 5 题就是这个故障）。

本模块只做两件事，不调用模型、不碰数据库：
1. 判断一段正文里是否混入了工具调用语法；
2. 把这些语法剥掉，返回干净文本，并告诉调用方“这轮发生过泄漏”。
"""

import re

# 单个标记：出现任意一个就说明这轮输出不可用。
LEAK_MARKERS: tuple[str, ...] = (
    "]<]minimax[>[",
    "<tool_call>",
    "</tool_call>",
    "<function_call>",
)

# 完整的 invoke 块可能跨多行，用 DOTALL 一次删掉整段。
_INVOKE_BLOCK = re.compile(r"<invoke\b.*?</invoke\s*>", re.S)
# 兜底：没有闭合的 invoke 标记、单独的 minimax 分隔符也一并清掉。
_STRAY_MARKERS = re.compile(
    r"<invoke\b[^>]*>|</invoke\s*>|<tool_call>|</tool_call\s*>|"
    r"<function_call>|</function_call\s*>|]<]minimax\[>\["
)


def contains_tool_call_syntax(text: str | None) -> bool:
    """正文里是否混入了工具调用语法（含 MiniMax 特殊 token）。"""

    if not text:
        return False
    return any(marker in text for marker in LEAK_MARKERS)


def clean_model_text(text: str | None) -> tuple[str, bool]:
    """清洗正文，返回 ``(干净文本, 是否检测到泄漏)``。

    没有泄漏时原样返回（只去掉首尾空白），避免影响正常回答里的尖括号内容。
    """

    raw = (text or "").strip()
    if not contains_tool_call_syntax(raw):
        return raw, False

    cleaned = _INVOKE_BLOCK.sub("", raw)
    cleaned = _STRAY_MARKERS.sub("", cleaned)
    # 删掉整块后可能剩下只有括号/尖括号的残行（例如 "]>"），这些不是内容。
    cleaned = re.sub(r"(?m)^[\s\]\}>]+$", "", cleaned)
    # 删除整段后常留下连续空行，压缩成最多一个空行。
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    cleaned = cleaned.strip(" \t\r\n]}>")
    return cleaned, True
