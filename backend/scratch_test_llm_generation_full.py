import asyncio
import os
import json
import logging
from sqlmodel import Session
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Setup basic logging to see agent process
logging.basicConfig(level=logging.INFO)

from app.database import build_engine, set_engine, init_db
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_resources import run_section_markdown_agent
from app.orchestration.llm import get_worker_llm

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
                        "content_requirements": ["绑定章节大纲", "引用学习者画像", "补充视频和动画"],
                    }
                ]
            }
        }
    }

async def run_test():
    # 1. Initialize in-memory SQLite database
    engine = build_engine("sqlite:///:memory:")
    set_engine(engine)
    init_db(engine)
    
    # 2. Seed test database
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    # 3. Instantiate real worker LLM (from environment)
    llm = get_worker_llm()
    print("Using LLM:", llm.model_name)
    
    # 4. Invoke agent to generate markdown
    state = {
        "user_id": "user-1",
        "course_knowledge": _outline(),
        "profile": _profile(),
        "year_learning_paths": _year_learning_paths(),
        "messages": [],
    }
    explicit_args = {
        "course_id": "year_3_course_1",
        "section_id": "1.1",
        "scope": "single_section",
    }
    
    print("\n--- Invoking run_section_markdown_agent ---")
    result = await run_section_markdown_agent(state, llm, explicit_args)
    
    # Check if there is an error
    if "error" in result and result.get("hard_error"):
        print("\n❌ Error returned by agent:", result["error"])
        return
        
    markdown_data = result["course_knowledge"]["section_markdowns"]["1.1"]
    print("\n✅ Successfully generated section markdown!")
    print(f"Title: {markdown_data['title']}")
    print(f"Generated at: {markdown_data['generated_at']}")
    print("\n--- Generated Markdown Content ---")
    print(markdown_data["markdown"][:1000] + "\n\n... (truncated) ...\n")
    
    # Verify if it used deterministic fallback
    is_fallback = "必须能解释和操作的核心能力" in markdown_data["markdown"]
    if is_fallback:
        print("❌ WARNING: The generated markdown is using the DETERMINISTIC FALLBACK content! The LLM call failed or was rejected by the quality gate.")
    else:
        print("🎉 SUCCESS: The generated markdown is UNIQUE and generated by the LLM (did not hit fallback)!")
        
    # Check if key RAG tools are mentioned
    keywords = ["pdfplumber", "re", "BeautifulSoup", "Unstructured", "OCR", "Markdown Table"]
    found_keywords = [kw for kw in keywords if kw.lower() in markdown_data["markdown"].lower()]
    print(f"Found technical keywords in generated text: {found_keywords}")

if __name__ == "__main__":
    asyncio.run(run_test())
