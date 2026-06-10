from __future__ import annotations

DEFAULT_FILL_MARKERS = (
    "随便帮我填",
    "不确定的你随便帮我填",
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
    return "默认" in normalized and any(marker in normalized for marker in DEFAULT_FILL_CONTEXT_MARKERS)
