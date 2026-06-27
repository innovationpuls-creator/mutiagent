import json
from app.main import app

if __name__ == "__main__":
    # 获取 FastAPI 自动生成的 OpenAPI 规范数据
    openapi_schema = app.openapi()
    print(json.dumps(openapi_schema, indent=2))
