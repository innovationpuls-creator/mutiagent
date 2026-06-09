import asyncio
import os
import json
import logging
from sqlmodel import Session
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO)

from app.database import build_engine, set_engine, init_db
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_resources import _markdown_input
from app.orchestration.llm import get_worker_llm
from langchain_core.messages import SystemMessage, HumanMessage
from app.orchestration.agents.prompts import SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT

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
    # Instantiate real worker LLM (from environment)
    llm = get_worker_llm()
    print("Using LLM:", llm.model_name)
    
    state = {
        "user_id": "user-1",
        "course_knowledge": _outline(),
        "profile": _profile(),
        "year_learning_paths": _year_learning_paths(),
        "messages": [],
    }
    
    # 4. Invoke LLM directly
    query = _markdown_input(state, _outline(), _outline()["sections"][1])
    
    messages = [
        SystemMessage(content=SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=query)
    ]
    
    print("\n--- Invoking LLM directly with System Prompt and Query ---")
    response = await llm.ainvoke(messages)
    
    print("\n--- Raw Response Content ---")
    print(response.content)
    print("\n--- Response Length ---")
    print(f"Length of response: {len(response.content)} characters")

if __name__ == "__main__":
    asyncio.run(run_test())
