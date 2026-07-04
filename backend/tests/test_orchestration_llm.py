from __future__ import annotations


def test_llm_factories_split_worker_and_thinking_modes(monkeypatch) -> None:
    import app.orchestration.llm as llm_module

    captured_calls: list[dict] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)
            self.kwargs = kwargs

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    llm_module._supervisor_llm = None
    llm_module._worker_llm = None
    llm_module._thinking_worker_llm = None
    llm_module._translation_llm = None

    supervisor = llm_module.get_supervisor_llm()
    worker = llm_module.get_worker_llm()
    thinking_worker = llm_module.get_thinking_worker_llm()
    translation = llm_module.get_translation_llm()

    assert supervisor.kwargs["timeout"] == 30
    assert worker.kwargs["timeout"] == 180
    assert thinking_worker.kwargs["timeout"] == 180
    assert translation.kwargs["timeout"] == 45
    assert supervisor.kwargs["max_tokens"] is None
    assert worker.kwargs["max_tokens"] == 8192
    assert thinking_worker.kwargs["max_tokens"] == 8192
    assert translation.kwargs["max_tokens"] == 4096
    assert translation.kwargs["streaming"] is False
    assert translation.kwargs["max_retries"] == 0
    assert supervisor.kwargs["extra_body"]["enable_thinking"] is False
    assert worker.kwargs["extra_body"]["enable_thinking"] is False
    assert thinking_worker.kwargs["extra_body"]["enable_thinking"] is True
    assert translation.kwargs["extra_body"]["enable_thinking"] is False


def test_llm_factories_cache_instances(monkeypatch) -> None:
    import app.orchestration.llm as llm_module

    build_count = 0

    class FakeChatOpenAI:
        def __init__(self, **_kwargs):
            nonlocal build_count
            build_count += 1

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    llm_module._supervisor_llm = None
    llm_module._worker_llm = None
    llm_module._thinking_worker_llm = None
    llm_module._translation_llm = None

    first = llm_module.get_thinking_worker_llm()
    second = llm_module.get_thinking_worker_llm()

    assert first is second
    assert build_count == 1


def test_graph_routes_long_reasoning_to_thinking_and_resource_generation_to_worker(
    monkeypatch,
) -> None:
    import app.orchestration.graph as graph_module

    supervisor_llm = object()
    worker_llm = object()
    thinking_llm = object()
    search_llm = object()
    received: dict[str, object] = {}

    async def dummy_node(_state):
        return {}

    monkeypatch.setattr(graph_module, "_graph", None)
    monkeypatch.setattr(graph_module, "get_supervisor_llm", lambda: supervisor_llm)
    monkeypatch.setattr(graph_module, "get_worker_llm", lambda: worker_llm)
    monkeypatch.setattr(graph_module, "get_thinking_worker_llm", lambda: thinking_llm)
    monkeypatch.setattr(graph_module, "get_search_worker_llm", lambda: search_llm)

    def profile_factory(llm):
        received["profile_agent"] = llm
        return dummy_node

    def learning_path_factory(llm):
        received["learning_path_agent"] = llm
        return dummy_node

    def course_knowledge_factory(llm):
        received["course_knowledge_agent"] = llm
        return dummy_node

    def supervisor_factory(llm):
        received["supervisor"] = llm
        return dummy_node

    def section_markdown_factory(llm):
        received["section_markdown_agent"] = llm
        return dummy_node

    def section_video_search_factory(llm):
        received["section_video_search_agent"] = llm
        return dummy_node

    def section_html_animation_factory(llm):
        received["section_html_animation_agent"] = llm
        return dummy_node

    monkeypatch.setattr(graph_module, "create_supervisor_node", supervisor_factory)
    monkeypatch.setattr(graph_module, "create_profile_agent_node", profile_factory)
    monkeypatch.setattr(
        graph_module, "create_learning_path_agent_node", learning_path_factory
    )
    monkeypatch.setattr(
        graph_module, "create_course_knowledge_agent_node", course_knowledge_factory
    )
    monkeypatch.setattr(
        graph_module, "create_section_markdown_agent_node", section_markdown_factory
    )
    monkeypatch.setattr(
        graph_module,
        "create_section_video_search_agent_node",
        section_video_search_factory,
    )
    monkeypatch.setattr(
        graph_module,
        "create_section_html_animation_agent_node",
        section_html_animation_factory,
    )

    graph_module.build_orchestration_graph()

    assert received["supervisor"] is supervisor_llm
    assert received["profile_agent"] is supervisor_llm
    assert received["learning_path_agent"] is thinking_llm
    assert received["course_knowledge_agent"] is worker_llm
    assert received["section_markdown_agent"] is worker_llm
    assert received["section_video_search_agent"] is search_llm
    assert received["section_html_animation_agent"] is worker_llm
    assert received["learning_path_agent"] is not worker_llm
    assert received["course_knowledge_agent"] is not thinking_llm
    assert received["section_markdown_agent"] is not thinking_llm
    assert received["section_html_animation_agent"] is not thinking_llm


def test_search_worker_llm_enables_search(monkeypatch) -> None:
    import app.orchestration.llm as llm_module

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    llm_module._search_worker_llm = None

    search_worker = llm_module.get_search_worker_llm()

    extra_body = search_worker.kwargs["extra_body"]
    assert extra_body["enable_thinking"] is True
    assert extra_body["enable_search"] is True
    assert extra_body["search_options"]["forced_search"] is True
    assert extra_body["search_options"]["search_strategy"] == "turbo"


def test_llm_factories_pass_extra_body_directly(monkeypatch) -> None:
    import app.orchestration.llm as llm_module

    captured_calls: list[dict] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)
            self.kwargs = kwargs

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    llm_module._search_worker_llm = None

    llm_module.get_search_worker_llm()

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert "extra_body" in call
    assert call["extra_body"]["enable_thinking"] is True
    assert call["extra_body"]["enable_search"] is True
