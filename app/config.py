import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file if it exists
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Settings(BaseSettings):
    # LLM Provider settings: "groq", "nvidia", or "simulated"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    
    # API Keys
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    
    # Default Models
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
    
    # Server configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    
    # Research defaults
    MAX_SEARCH_RESULTS: int = 5
    MAX_SCRAPE_PAGES: int = 4
    REQUEST_TIMEOUT_SECONDS: int = 15
    USER_AGENT: str = "AutonomousResearchFactChecker/1.0 (Academic & Fact-Checking Research; Contact: researcher@example.local)"

    class Config:
        arbitrary_types_allowed = True

settings = Settings()

def update_runtime_settings(provider: str = None, groq_key: str = None, nvidia_key: str = None, tavily_key: str = None, groq_model: str = None, nvidia_model: str = None):
    """Updates runtime configuration and environment variables."""
    global settings
    if provider:
        settings.LLM_PROVIDER = provider
        os.environ["LLM_PROVIDER"] = provider
    if groq_key is not None:
        settings.GROQ_API_KEY = groq_key
        os.environ["GROQ_API_KEY"] = groq_key
    if nvidia_key is not None:
        settings.NVIDIA_API_KEY = nvidia_key
        os.environ["NVIDIA_API_KEY"] = nvidia_key
    if tavily_key is not None:
        settings.TAVILY_API_KEY = tavily_key
        os.environ["TAVILY_API_KEY"] = tavily_key
    if groq_model:
        settings.GROQ_MODEL = groq_model
        os.environ["GROQ_MODEL"] = groq_model
    if nvidia_model:
        settings.NVIDIA_MODEL = nvidia_model
        os.environ["NVIDIA_MODEL"] = nvidia_model
