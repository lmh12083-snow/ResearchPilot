from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+pymysql://user:password@localhost/researchpilot"

    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24  # 24 hours

    # File uploads
    UPLOAD_PATH: str = "./uploads"

    # Chunking
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    # Embedding
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # Vector store
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # API
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:5173"]

    # LLM — reads from DEEPSEEK_API_KEY env var automatically
    DEEPSEEK_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # Web Search
    WEB_SEARCH_PROVIDER: str = "duckduckgo"  # duckduckgo | bing
    BING_SEARCH_API_KEY: str = ""  # https://portal.azure.com -> Cognitive Services

    # Paper comparison
    COMPARE_MAX_PAPERS: int = 5  # max papers in one comparison

    model_config = {"env_file": "../.env", "case_sensitive": True}


settings = Settings()
