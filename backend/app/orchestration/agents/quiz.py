from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any


PASSING_SCORE = 70
SUPPORTED_QUESTION_TYPES = {"single_choice", "code", "image_upload"}


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_fallback_quiz_questions(chapter_id: str, chapter_title: str) -> list[dict[str, Any]]:
    title = chapter_title or f"第 {chapter_id} 章"
    return [
        {
            "question_id": "q1",
            "type": "single_choice",
            "prompt": f"{title} 的首要学习目标是什么？",
            "options": [
                {"option_id": "A", "text": "识别本章核心概念与约束"},
                {"option_id": "B", "text": "跳过本章直接进入项目交付"},
                {"option_id": "C", "text": "只记住术语名称"},
                {"option_id": "D", "text": "只关注工具界面"},
            ],
            "correct_option_id": "A",
            "points": 30,
        },
        {
            "question_id": "q2",
            "type": "code",
            "prompt": "写一个小函数或伪代码，说明你会如何检查本章任务是否达成。",
            "options": [],
            "starter_code": "def check_goal(result):\n    pass\n",
            "points": 40,
        },
        {
            "question_id": "q3",
            "type": "image_upload",
            "prompt": "上传或描述一张你绘制的本章思路图，并说明其中的关键关系。",
            "options": [],
            "image_prompt": "请上传本章思路图，或填写图片说明。",
            "points": 30,
        },
    ]


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
        normalized.append(
            {
                "question_id": question_id,
                "type": question_type,
                "prompt": prompt,
                "options": item.get("options") if isinstance(item.get("options"), list) else [],
                "starter_code": _clean_text(item.get("starter_code")),
                "image_prompt": _clean_text(item.get("image_prompt")),
                "points": int(points) if isinstance(points, int) else 0,
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
    summary = _clean_text(value.get("summary")) or ("已经通过。" if score > PASSING_SCORE else "建议复习后再试一次。")
    return {
        "score": score,
        "passed": score > PASSING_SCORE,
        "question_results": question_results,
        "summary": summary,
    }


async def generate_quiz_questions(
    llm: Any,
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_context: str,
) -> list[dict[str, Any]]:
    prompt = (
        "请为当前章节生成 3 道测验题，必须覆盖 single_choice、code、image_upload。"
        "只输出 JSON 数组，每题包含 question_id、type、prompt、options、starter_code、image_prompt、points。\n"
        f"chapter_id: {chapter_id}\nchapter_title: {chapter_title}\nchapter_context:\n{chapter_context}"
    )
    if not hasattr(llm, "ainvoke"):
        return build_fallback_quiz_questions(chapter_id, chapter_title)
    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", response)
    try:
        return normalize_quiz_questions(json.loads(str(content)))
    except Exception:
        return build_fallback_quiz_questions(chapter_id, chapter_title)


async def grade_quiz_answers(llm: Any, *, questions: list[dict[str, Any]], answers: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "请根据题目和用户答案给出 0-100 分整数分数。"
        "只输出 JSON 对象，字段为 score、question_results、summary。\n"
        f"questions:\n{json.dumps(questions, ensure_ascii=False)}\n"
        f"answers:\n{json.dumps(answers, ensure_ascii=False)}"
    )
    if not hasattr(llm, "ainvoke"):
        return normalize_grading_result({"score": 0, "question_results": [], "summary": "判题模型不可用。"})
    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", response)
    return normalize_grading_result(json.loads(str(content)))


async def stream_forest_ai_response(llm: Any, *, message: str, context: dict[str, Any]) -> AsyncGenerator[str, None]:
    prompt = (
        "你是 Forest AI，只围绕当前章节测验答疑。"
        "根据当前题目、用户答案和判题结果给出清晰解析。\n"
        f"context:\n{json.dumps(context, ensure_ascii=False)}\n"
        f"user_message:\n{message}"
    )
    if not hasattr(llm, "astream"):
        yield "我会先看当前题目、你的答案和判题反馈，再给出解析。"
        return
    async for chunk in llm.astream(prompt):
        content = getattr(chunk, "content", "")
        if content:
            yield str(content)
