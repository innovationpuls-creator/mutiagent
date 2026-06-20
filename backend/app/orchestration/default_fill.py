from __future__ import annotations

DEFAULT_FILL_MARKERS = (
    "随便帮我填",
    "不确定的你随便帮我填",
    "直接生成",
    "你直接生成",
    "帮我直接生成",
    "不用问了",
    "不用再问了",
    "不需要这么详细",
    "跳过",
    "先跳过",
    "不用这么详细",
    "快速生成",
    "直接帮我生成",
)
DEFAULT_FILL_CONTEXT_MARKERS = (
    "画像",
    "补全",
    "填",
    "生成",
)


def allows_default_profile_fill(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if any(marker in normalized for marker in DEFAULT_FILL_MARKERS):
        return True
    return "默认" in normalized and any(
        marker in normalized for marker in DEFAULT_FILL_CONTEXT_MARKERS
    )
