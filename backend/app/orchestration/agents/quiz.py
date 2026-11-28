from __future__ import annotations

from typing import Any

PASSING_SCORE = 70
SUPPORTED_QUESTION_TYPES = {"single_choice", "code", "image_upload"}


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_options(options_raw: object) -> list[dict[str, str]]:  # noqa: C901
    if not isinstance(options_raw, list):
        return []
    normalized_opts = []
    for idx, opt in enumerate(options_raw):
        if isinstance(opt, dict):
            option_id = _clean_text(opt.get("option_id"))
            text = _clean_text(opt.get("text"))
            if not option_id:
                option_id = chr(65 + idx)
            if not text:
                text = (
                    _clean_text(opt.get("option_text"))
                    or _clean_text(opt.get("label"))
                    or ""
                )
            normalized_opts.append({"option_id": option_id, "text": text})
        elif isinstance(opt, str):
            opt_str = opt.strip()
            option_id = ""
            text = opt_str
            if (
                len(opt_str) > 2
                and opt_str[0].isalpha()
                and opt_str[1] in (".", ":", "、", " ")
            ):
                option_id = opt_str[0].upper()
                text = opt_str[2:].strip()
            elif (
                len(opt_str) > 1
                and opt_str[0].isalpha()
                and opt_str[0].isupper()
                and idx < 26
            ):
                expected_letter = chr(65 + idx)
                if opt_str.startswith(expected_letter):
                    option_id = expected_letter
                    text = opt_str[len(expected_letter) :].strip()
                    if text.startswith((".", ":", "、", " ")):
                        text = text[1:].strip()

            if not option_id:
                option_id = chr(65 + idx)
            normalized_opts.append({"option_id": option_id, "text": text})
    return normalized_opts


def normalize_quiz_questions(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("题目不能为空")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError("题目格式不正确")
        question_type = _clean_text(item.get("type"))
        if question_type not in SUPPORTED_QUESTION_TYPES:
            raise ValueError("题目类型不支持")
        question_id = _clean_text(item.get("question_id")) or f"q{index}"
        prompt = _clean_text(item.get("prompt"))
        if not prompt:
            raise ValueError("题干不能为空")
        points = item.get("points")

        correct_val = _clean_text(item.get("correct_option_id")).strip()
        if (
            len(correct_val) > 2
            and correct_val[0].isalpha()
            and correct_val[1] in (".", ":", "、", " ")
        ):
            correct_option_id = correct_val[0].upper()
        else:
            correct_option_id = correct_val.upper()

        kp_ids = item.get("knowledge_point_ids")
        if isinstance(kp_ids, list):
            knowledge_point_ids = [str(kp).strip() for kp in kp_ids if str(kp).strip()]
        else:
            knowledge_point_ids = []

        normalized.append(
            {
                "question_id": question_id,
                "type": question_type,
                "prompt": prompt,
                "options": _normalize_options(item.get("options")),
                "correct_option_id": correct_option_id,
                "starter_code": _clean_text(item.get("starter_code")),
                "image_prompt": _clean_text(item.get("image_prompt")),
                "points": int(points) if isinstance(points, int) else 0,
                "knowledge_point_ids": knowledge_point_ids,
            }
        )
    return normalized


def normalize_grading_result(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("判题结果格式不正确")
    score_value = value.get("score")
    if not isinstance(score_value, int):
        raise ValueError("判题分数缺失")
    score = max(0, min(100, score_value))
    question_results = value.get("question_results")
    if not isinstance(question_results, list):
        question_results = []
    summary = _clean_text(value.get("summary")) or (
        "已经通过。" if score > PASSING_SCORE else "建议复习后再试一次。"
    )
    return {
        "score": score,
        "passed": score > PASSING_SCORE,
        "question_results": question_results,
        "summary": summary,
    }
