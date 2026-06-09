import asyncio
import os
import json
import logging
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO)

from app.orchestration.llm import get_worker_llm
from langchain_core.messages import SystemMessage, HumanMessage
from app.orchestration.agents.prompts import SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.models import SectionHtmlAnimationOutput
from app.orchestration.agents.course_resources import (
    _animation_input,
    _normalize_animations,
    _normalized_animation_quality_issue,
    _clean_text
)

def _outline() -> dict:
    return {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发",
        "grade_year": "year_3",
        "personalization_summary": "先完成非结构化文档解析，再进入后续阶段。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "数据预处理与向量化流水线",
                "order_index": 1,
                "description": "非结构化文档解析与噪声清洗策略。",
                "key_knowledge_points": ["文档结构树分析与段落边界识别", "正则表达式与启发式规则过滤噪声"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "非结构化文档解析与噪声清洗策略",
                "order_index": 2,
                "description": "掌握多格式文档的自动化提取方法，消除页眉页脚、乱码等干扰因素，保证原始语料质量。",
                "key_knowledge_points": ["文档结构树分析与段落边界识别", "正则表达式与启发式规则过滤噪声", "表格与图片Alt文本的降级处理方案"],
            }
        ],
        "learning_sequence": ["第一章：数据预处理与向量化流水线"],
        "total_estimated_hours": "8 小时",
    }

def _profile() -> dict:
    return {
        "type": "basic_profile",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "learning_method_preference": "项目驱动学习",
            "content_preference": ["视频", "文档", "代码实践"],
            "weekly_available_time": "每天 12 小时项目驱动",
            "constraints": "需要先补齐需求边界表达",
        },
        "text": "画像强调项目驱动、视频文档结合，并需要补齐需求边界表达。",
    }

def _year_learning_paths() -> dict:
    return {
        "year_3": {
            "schema_version": "learning_path.v2.course_node",
            "current_learning_course": {
                "grade_id": "year_3",
                "course_node_id": "year_3_course_1",
                "course_or_chapter_theme": "AI 应用开发",
                "course_goal": "完成作品级 Agent 项目闭环",
                "current_focus": "先把需求拆解落实为可验收产出",
                "progress_state": "in_progress",
                "next_action": "完成第一章数据预处理与向量化流水线",
            },
            "resource_generation_contract": {
                "resource_directions": [
                    {
                        "resource_direction_id": "year_3_course_1_resource",
                        "target_node_ids": ["year_3_course_1"],
                        "resource_type": "文档",
                        "generation_goal": "围绕作品级 Agent 项目闭环生成教学资源",
                        "content_requirements": ["绑定章节大纲", "引用学习者画像", "补充视频 and 动画"],
                    }
                ]
            }
        }
    }

async def run_test():
    llm = get_worker_llm()
    print("Using LLM:", llm.model_name)
    
    outline = _outline()
    section = outline["sections"][1]
    section_id = section["section_id"]
    
    # Construct section markdown and animation brief
    outline["section_markdowns"] = {
        section_id: {
            "section_id": section_id,
            "parent_section_id": "1",
            "title": "非结构化文档解析与噪声清洗策略",
            "markdown": "# 1.1 非结构化文档解析与噪声清洗策略\n\n## 学习目标\n...\n<!-- animation:id=anim_1 -->\n...",
            "animation_briefs": [
                {
                    "animation_id": "anim_1",
                    "title": "非结构化文档解析流",
                    "concept": "展示非结构化文档从输入到分块、清洗再输出的过程",
                    "visual_elements": ["输入文档", "解析引擎", "正则过滤", "清洗后文本"],
                    "motion": "元素在页面中流畅地移动，点击下一步按钮推进阶段，展示解析前后的文本对比并支持重置",
                    "space": "高度 320px",
                    "placement_hint": "核心概念之后"
                }
            ],
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "文档解析演示",
                    "purpose": "说明如何解析"
                }
            ]
        }
    }
    
    state = {
        "user_id": "user-1",
        "course_knowledge": outline,
        "profile": _profile(),
        "year_learning_paths": _year_learning_paths(),
        "messages": [],
    }
    
    # 1. Generate Query using _animation_input
    query = _animation_input(state, outline, section)
    
    messages = [
        SystemMessage(content=SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=query)
    ]
    
    print("\n--- Invoking LLM for HTML Animation Generation ---")
    response = await llm.ainvoke(messages)
    
    print("\n--- Raw Response Content ---")
    print(response.content)
    
    # 2. Parse JSON response
    try:
        raw_json = json.loads(response.content)
        print("\n--- Successfully parsed JSON ---")
    except Exception as e:
        # Try finding JSON block in markdown
        print("\n--- JSON parsing failed, attempting markdown extraction ---")
        try:
            cleaned = response.content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            raw_json = json.loads(cleaned.strip())
            print("Successfully extracted and parsed JSON from markdown block!")
        except Exception as e2:
            print("Failed to parse response as JSON. Error:", e2)
            return

    # 3. Validate with SectionHtmlAnimationOutput Pydantic schema
    try:
        pydantic_output = SectionHtmlAnimationOutput.model_validate(raw_json)
        print("Pydantic validation passed successfully!")
    except Exception as e:
        print("Pydantic validation FAILED! Error:", e)
        return
        
    # 4. Normalize and run quality check
    animation_briefs = outline["section_markdowns"][section_id]["animation_briefs"]
    animations = _normalize_animations(pydantic_output.animations, animation_briefs)
    
    quality_issue = _normalized_animation_quality_issue(animations, animation_briefs, section)
    if quality_issue:
        print("\n❌ Quality check FAILED: ", quality_issue)
    else:
        print("\n✅ Quality check PASSED successfully!")
        
        # Print generated HTML
        print("\n--- Generated HTML Preview ---")
        print(animations[0]["html"][:1000] + "\n... (truncated) ...")
        
        # Check if JavaScript exists in generated HTML
        if "<script>" in animations[0]["html"]:
            print("\n🎉 Found JavaScript code in the generated HTML animation!")
        else:
            print("\n⚠️ Warning: No JavaScript found in the generated HTML.")

if __name__ == "__main__":
    asyncio.run(run_test())
