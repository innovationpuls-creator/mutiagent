from __future__ import annotations

import json
import re


class DifyAnswerParseError(ValueError):
    pass


def parse_json_answer(raw: dict) -> dict:
    raw_answer = raw.get("answer", "")
    if not isinstance(raw_answer, str):
        raise DifyAnswerParseError("Dify answer must be a string")

    cleaned = raw_answer.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DifyAnswerParseError("Dify answer is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise DifyAnswerParseError("Dify answer JSON must be an object")
    return parsed
