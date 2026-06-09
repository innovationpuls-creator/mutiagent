import pytest
from unittest.mock import patch
from app.schemas import ChatMessageRequest
from langchain_core.messages import HumanMessage
from tests.test_orchestration_api import chat_app, _register_user, _auth_header

def test_multimodal_request_schema():
    req = ChatMessageRequest(
        session_id="test-session",
        message="explain this drawing",
        image_attachment="data:image/png;base64,iVBORw0KGgoAAAANS"
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
                "image_attachment": image_data
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
        assert last_msg.content[1] == {"type": "image_url", "image_url": {"url": image_data}}
