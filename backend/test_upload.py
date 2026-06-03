import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv(".env")
api_key = os.getenv("DIFY_PROFILE_AGENT_API_KEY")
url = os.getenv("DIFY_API_URL", "http://localhost/v1").rstrip("/") + "/files/upload"

async def main():
    async with httpx.AsyncClient() as client:
        files = {"file": ("test.txt", b"Hello World", "text/plain")}
        data = {"user": "test_user"}
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files
        )
        print(resp.status_code, resp.text)

asyncio.run(main())
