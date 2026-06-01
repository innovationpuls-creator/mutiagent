import asyncio
import json
import uuid

from app.orchestration.dify_client import DifyClient
from app.orchestration.graph import create_orchestration_graph
from app.orchestration.state import OrchestrationState


async def single_turn(graph, state: OrchestrationState) -> OrchestrationState:
    config = {"configurable": {"thread_id": state["user_id"]}}
    result = await graph.ainvoke(state, config)
    return result


def print_state(state: OrchestrationState, turn: int) -> None:
    aj = state.get("answer_json", {})
    print(f"\n{'='*60}")
    print(f"Turn {turn} | Phase: {state.get('phase')} | ConvID: {state.get('conversation_id', '')[:8]}...")
    print(f"{'='*60}")
    ct = aj.get("type", "?")
    st = aj.get("stage", "?")
    print(f"Dify type: {ct} | stage: {st}")
    if ct == "collecting":
        confirmed = aj.get("confirmed_info", {})
        filled = {k: v for k, v in confirmed.items() if v}
        print(f"Filled fields ({len(filled)}): {list(filled.keys())}")
        print(f"Question text: {aj.get('text', '')[:200]}...")
    elif ct == "basic_profile":
        print(f"Profile text: {aj.get('text', '')[:500]}...")
    else:
        print(f"Raw text: {aj.get('text', '')[:200]}...")


async def main():
    client = DifyClient()
    graph = create_orchestration_graph(client)

    user_id = f"test-{uuid.uuid4().hex[:8]}"
    state: OrchestrationState = {
        "query": "你好，我想学习数据结构",
        "user_id": user_id,
        "conversation_id": "",
        "intent_conversation_id": "",
        "intent_raw": {},
        "intent": "",
        "route_status": "",
        "dify_raw": {},
        "answer_json": {},
        "phase": "collecting",
        "error": "",
    }

    simulated_answers = [
        "大三，软件工程",
        "我偏好视频和实践，不需要太强的引导",
        "有一定编程基础，擅长后端，薄弱的是算法和系统设计",
        "近期想做一个小项目，长期想进大厂，每周大概8小时",
    ]

    state = await single_turn(graph, state)
    print_state(state, 1)

    answer_idx = 0
    for turn in range(2, 20):
        if state["phase"] == "completed":
            print("\nChatflow completed!")
            break
        if answer_idx < len(simulated_answers):
            state["query"] = simulated_answers[answer_idx]
            answer_idx += 1
        else:
            state["query"] = "可以了，生成画像吧"

        state = await single_turn(graph, state)
        print_state(state, turn)

    print(f"\nFinal phase: {state['phase']}")
    if state["phase"] == "completed":
        print("Full profile generated successfully!")
        print(json.dumps(state["answer_json"], ensure_ascii=False, indent=2)[:2000])
    else:
        print("Max turns reached without completion.")


if __name__ == "__main__":
    asyncio.run(main())
