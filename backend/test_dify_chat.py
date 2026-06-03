import asyncio
from dotenv import load_dotenv
import json

from app.orchestration.dify_client import DifyClient

load_dotenv()

async def test_chat():
    client = DifyClient()
    
    contexts = {
        "user_profile": {"type": "basic_profile", "stage": "generated", "text": "这是一个测试画像。"},
    }
    
    print("Uploading contexts...")
    files = await client.upload_contexts("test_user_id", contexts)
    print("Uploaded:", files)
    
    print("Sending chat message...")
    response = await client.chat_streaming_blocking(
        query="生成学习路径",
        user_id="test_user_id",
        inputs={"userinput.query": "生成学习路径"},
        files=files
    )
    print(response.answer)

if __name__ == "__main__":
    asyncio.run(test_chat())
