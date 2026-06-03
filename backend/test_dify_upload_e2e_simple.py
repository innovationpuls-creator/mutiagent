import asyncio
from dotenv import load_dotenv
import json

from app.orchestration.dify_client import DifyClient

load_dotenv()

async def test_upload():
    # 2. Create client
    client = DifyClient()
    
    # 3. Simulate contexts extraction
    contexts = {
        "user_profile": {"type": "basic_profile", "stage": "generated", "text": "这是一个测试画像。"},
        "dummy_context": "just a string context"
    }
    
    print("Uploading contexts...")
    files = await client.upload_contexts("test_user_id", contexts)
    
    print("Files array to send to Dify:")
    print(json.dumps(files, indent=2))
    
    # Check if files array has correct format
    assert len(files) == 2, f"Expected 2 files, got {len(files)}"
    for f in files:
        assert f["type"] == "document"
        assert f["transfer_method"] == "local_file"
        assert "upload_file_id" in f
        
    print("\nSUCCESS! Contexts are correctly converted to files and uploaded.")

if __name__ == "__main__":
    asyncio.run(test_upload())
