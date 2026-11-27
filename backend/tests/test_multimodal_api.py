import pytest
from pydantic import ValidationError

from app.schemas import ChatMessageRequest, ForestAiStreamRequest

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
