import os
import uvicorn
from app.config import settings

if __name__ == "__main__":
    port = int(os.getenv("PORT", settings.PORT))
    host = os.getenv("HOST", settings.HOST)
    print(f"================================================================")
    print(f"  Autonomous Research & Fact-Checking Assistant")
    print(f"  Running on: http://{host}:{port}")
    print(f"  LLM Provider: {settings.LLM_PROVIDER}")
    print(f"================================================================")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
