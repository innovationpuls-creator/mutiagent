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
            "knowledge_point_ids": [],
        },
        {
            "question_id": "q2",
            "type": "code",
            "prompt": "写一个小函数或伪代码，说明你会如何检查本章任务是否达成。",
            "options": [],
            "starter_code": "def check_goal(result):\n    pass\n",
            "points": 40,
            "knowledge_point_ids": [],
        },
        {
            "question_id": "q3",
            "type": "image_upload",
            "prompt": "上传或描述一张你绘制的本章思路图，并说明其中的关键关系。",
            "options": [],
            "image_prompt": "请上传本章思路图，或填写图片说明。",
            "points": 30,
            "knowledge_point_ids": [],
        },
    ]


def _normalize_options(options_raw: object) -> list[dict[str, str]]:
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
                text = _clean_text(opt.get("option_text")) or _clean_text(opt.get("label")) or ""
            normalized_opts.append({"option_id": option_id, "text": text})
        elif isinstance(opt, str):
            opt_str = opt.strip()
            option_id = ""
            text = opt_str
            if len(opt_str) > 2 and opt_str[0].isalpha() and opt_str[1] in (".", ":", "、", " "):
                option_id = opt_str[0].upper()
                text = opt_str[2:].strip()
            elif len(opt_str) > 1 and opt_str[0].isalpha() and opt_str[0].isupper() and idx < 26:
                expected_letter = chr(65 + idx)
                if opt_str.startswith(expected_letter):
                    option_id = expected_letter
                    text = opt_str[len(expected_letter):].strip()
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
        if len(correct_val) > 2 and correct_val[0].isalpha() and correct_val[1] in (".", ":", "、", " "):
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
    summary = _clean_text(value.get("summary")) or ("已经通过。" if score > PASSING_SCORE else "建议复习后再试一次。")
    return {
        "score": score,
        "passed": score > PASSING_SCORE,
        "question_results": question_results,
        "summary": summary,
    }


def _prepare_answers_for_grading_prompt(value: object) -> object:
    if isinstance(value, dict):
        prepared: dict[str, Any] = {}
        for key, item in value.items():
            if key == "data_url" and isinstance(item, str):
                prepared[key] = f"[已上传图片，data_url 已省略，字符数: {len(item)}]"
            else:
                prepared[key] = _prepare_answers_for_grading_prompt(item)
        return prepared
    if isinstance(value, list):
        return [_prepare_answers_for_grading_prompt(item) for item in value]
    return value


async def generate_quiz_questions(
    llm: Any,
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_context: str,
    knowledge_point_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    kp_instruction = ""
    if knowledge_point_ids:
        kp_list = ", ".join(knowledge_point_ids)
        kp_instruction = (
            f"\n【知识点标注要求】\n"
            f"本章节包含以下知识点 ID：{kp_list}\n"
            f"每道题必须包含 `knowledge_point_ids` 字段，从上述列表中选取与该题考查内容最相关的知识点 ID（可多选）。\n"
        )

    prompt = (
        "请为当前章节生成 3 道测验题，必须覆盖 single_choice、code、image_upload。\n"
        "【重要设计要求】\n"
        "生成的测验题必须紧密结合本章节中的「练习任务」与「检查标准」内容来设计：\n"
        "1. 单选题 (single_choice)：考查「练习任务」或「检查标准」中的核心概念、要求或关键知识点。\n"
        "2. 代码题 (code)：要求用户编写一段代码或伪代码，来完成/辅助完成「练习任务」，或者编写测试/验证代码以验证「检查标准」中的某项指标是否通过。必须包含 starter_code 作为起点。\n"
        "3. 图片上传题 (image_upload)：要求用户上传完成「练习任务」后的运行效果截图、架构/思路图或结果图，并在 prompt 中说明具体的截图/图片要求。\n\n"
        "只输出 JSON 数组，每题包含 question_id、type、prompt、options、correct_option_id（如果是单选题，请填写正确选项 ID，如 A、B 等）、starter_code、image_prompt、points、knowledge_point_ids。\n"
        "【特别注意】：如果是单选题 (single_choice)，其 options 字段必须为包含选项字典的数组，每个选项字典格式为：{\"option_id\": \"选项ID，如A/B/C/D\", \"text\": \"选项内容\"}。如果是代码题或图片上传题，options 字段为空数组 []。\n"
        f"{kp_instruction}"
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
    grading_answers = _prepare_answers_for_grading_prompt(answers)
    prompt = (
        "请根据题目和用户答案给出 0-100 分整数分数。"
        "只输出 JSON 对象，字段为 score、question_results、summary。"
        "summary 必须使用中文，简要说明判题依据。\n"
        f"questions:\n{json.dumps(questions, ensure_ascii=False)}\n"
        f"answers:\n{json.dumps(grading_answers, ensure_ascii=False)}"
    )
    if not hasattr(llm, "ainvoke"):
        return normalize_grading_result({"score": 0, "question_results": [], "summary": "判题模型不可用。"})
    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", response)
    return normalize_grading_result(json.loads(str(content)))


async def stream_forest_ai_response(
    llm: Any,
    *,
    message: str,
    context: dict[str, Any],
    image_attachment: str | None = None,
) -> AsyncGenerator[str, None]:
    if image_attachment:
        prompt = [
            {
                "type": "text",
                "text": (
                    "你是 Forest AI，只围绕当前章节测验答疑。"
                    "根据当前题目、用户答案和判题结果给出清晰解析。\n"
                    f"context:\n{json.dumps(context, ensure_ascii=False)}\n"
                    f"user_message:\n{message}"
                )
            },
            {"type": "image_url", "image_url": {"url": image_attachment}}
        ]
    else:
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
