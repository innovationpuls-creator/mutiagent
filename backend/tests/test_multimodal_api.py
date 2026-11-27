from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from app.schemas import ChatMessageRequest, ForestAiStreamRequest
from tests.test_orchestration_api import _auth_header, _register_user, chat_app

VALID_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_multimodal_request_schema():
    req = ChatMessageRequest(
        session_id="test-session",
        message="explain this drawing",
        image_attachment=VALID_IMAGE_DATA_URL,
    )
    assert req.image_attachment is not None
    assert "base64" in req.image_attachment


def test_multimodal_request_rejects_unsupported_or_oversized_images():
    with pytest.raises(ValidationError):
        ChatMessageRequest(
            session_id="test-session",
            message="explain this drawing",
            image_attachment="data:text/html;base64,SGVsbG8=",
        )

    with pytest.raises(ValidationError):
        ForestAiStreamRequest(
            course_node_id="course",
            chapter_id="chapter",
            message="explain this drawing",
            active_question_context={
                "course_node_id": "course",
                "chapter_id": "chapter",
            },
            image_attachment="data:image/png;base64," + ("A" * (12 * 1024 * 1024)),
        )


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

        image_data = VALID_IMAGE_DATA_URL
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
