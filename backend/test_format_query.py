import json

def format_query_with_contexts(query: str, contexts: dict) -> str:
    if not contexts:
        return query
    
    parts = []
    parts.append("<system_context>")
    parts.append("以下是当前用户的上下文信息：")
    for k, v in contexts.items():
        if not v:
            continue
        v_str = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        if v_str in ("{}", '""', ""):
            continue
        parts.append(f"<{k}>\n{v_str}\n</{k}>")
    parts.append("</system_context>\n")
    parts.append(f"[User Query]\n{query}")
    return "\n".join(parts)

print(format_query_with_contexts("生成学习路径", {"user_profile": {"grade": "大三"}, "learning_path": {}}))
