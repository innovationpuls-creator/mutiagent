from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from app.schemas import ChatMessageRequest
from tests.postgres import postgresql_test_url
from tests.test_orchestration_api import _auth_header, _register_user, chat_app


def test_multimodal_request_schema():
    req = ChatMessageRequest(
        session_id="test-session",
        message="explain this drawing",
        image_attachment="data:image/png;base64,iVBORw0KGgoAAAANS",
    )
    assert req.image_attachment is not None
    assert "base64" in req.image_attachment


@patch("app.api.orchestration.stream_orchestration_events")
def test_send_message_multimodal_stream(mock_stream, tmp_path):
    captured_messages = []

    async def mock_events(state):
        captured_messages.extend(state["messages"])
        yield {"event": "session_started", "session_id": state["session_id"]}
        yield {"event": "message_completed", "full_text": "I see the drawing"}
        yield {"event": "session_completed", "session_id": state["session_id"]}

    mock_stream.side_effect = mock_events

    with chat_app(tmp_path) as client:
        token = _register_user(client, "multimodal@example.com", "password123")
        start_resp = client.post(
            "/api/chat/start",
            json={"query": "开始"},
            headers=_auth_header(token),
        )
        session_id = start_resp.json()["session_id"]

        image_data = "data:image/png;base64,iVBORw0KGgoAAAANS"
        response = client.post(
            "/api/chat/message",
            json={
                "session_id": session_id,
                "message": "explain this drawing",
                "image_attachment": image_data,
            },
            headers=_auth_header(token),
        )

        assert response.status_code == 200
        assert "session_started" in response.text
        assert "I see the drawing" in response.text

        # Verify that the last message is a multimodal HumanMessage
        assert len(captured_messages) > 0
        last_msg = captured_messages[-1]
        assert isinstance(last_msg, HumanMessage)
        assert isinstance(last_msg.content, list)
        assert last_msg.content[0] == {"type": "text", "text": "explain this drawing"}
        assert last_msg.content[1] == {
            "type": "image_url",
            "image_url": {"url": image_data},
        }


from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestration.agents.quiz import stream_forest_ai_response
from tests.test_forest_api import _auth_headers, _seed_forest_data


@pytest.mark.anyio
async def test_stream_forest_ai_response_multimodal():
    mock_llm = MagicMock()

    captured_prompts = []

    async def mock_astream(prompt):
        captured_prompts.append(prompt)
        chunk = MagicMock()
        chunk.content = "parsed analysis"
        yield chunk

    mock_llm.astream.side_effect = mock_astream

    # 1. Test with image_attachment
    chunks = []
    async for chunk in stream_forest_ai_response(
        mock_llm,
        message="what is this?",
        context={"question": "some-question"},
        image_attachment="data:image/png;base64,xyz",
    ):
        chunks.append(chunk)

    assert chunks == ["parsed analysis"]
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert isinstance(prompt, list)
    assert len(prompt) == 2
    assert prompt[0]["type"] == "text"
    assert "你是 Forest AI" in prompt[0]["text"]
    assert "what is this?" in prompt[0]["text"]
    assert prompt[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,xyz"},
    }

    # 2. Test without image_attachment (fallback/existing text prompt logic)
    captured_prompts.clear()
    chunks.clear()
    async for chunk in stream_forest_ai_response(
        mock_llm,
        message="what is this?",
        context={"question": "some-question"},
        image_attachment=None,
    ):
        chunks.append(chunk)

    assert chunks == ["parsed analysis"]
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert isinstance(prompt, str)
    assert "你是 Forest AI" in prompt
    assert "what is this?" in prompt


def test_stream_forest_ai_api_multimodal(tmp_path):
    database_url = postgresql_test_url(tmp_path, "forest-ai-multimodal-test")
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)

    captured_kwargs = {}

    async def fake_stream_response(*args, **kwargs):
        captured_kwargs.update(kwargs)
        yield "Forest AI response chunk"

    with patch("app.api.forest.stream_forest_ai_response", fake_stream_response):
        response = client.post(
            "/api/forest/ai/stream",
            json={
                "course_node_id": "year_3_course_2",
                "chapter_id": "1",
                "quiz_id": None,
                "question_id": None,
                "message": "what is this?",
                "active_question_context": {
                    "course_node_id": "year_3_course_2",
                    "chapter_id": "1",
                    "quiz_id": None,
                    "question_id": None,
                    "question": None,
                    "answer": None,
                    "grading_result": None,
                },
                "image_attachment": "data:image/png;base64,xyz",
            },
            headers=_auth_headers(user_uid),
        )

    assert response.status_code == 200
    assert "Forest AI response chunk" in response.text
    assert captured_kwargs.get("image_attachment") == "data:image/png;base64,xyz"
