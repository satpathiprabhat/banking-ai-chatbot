import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "apiKey.env"

# Load app env once in a central place so config does not depend on import order.
load_dotenv(dotenv_path=ENV_PATH)


@dataclass(frozen=True)
class Settings:
    jwt_secret_key: str
    admin_username: str
    admin_password: str
    service_token: str
    llm_provider: str
    llm_model_id: str
    llm_base_url: str
    llm_api_key: str
    gemini_base_url: str
    gemini_api_key: str
    openai_base_url: str
    openai_api_key: str
    embedding_model: str
    rag_index_path: str
    rag_meta_path: str
    rag_top_k: int
    mock_locked_status: bool

    @property
    def auth_configured(self) -> bool:
        return bool(self.jwt_secret_key and self.admin_username and self.admin_password)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        jwt_secret_key=(os.getenv("JWT_SECRET_KEY") or "").strip(),
        admin_username=(os.getenv("ADMIN_USERNAME") or "").strip(),
        admin_password=(os.getenv("ADMIN_PASSWORD") or "").strip(),
        service_token=(os.getenv("SERVICE_TOKEN") or "").strip(),
        llm_provider=(os.getenv("LLM_PROVIDER") or "gemini").strip().lower(),
        llm_model_id=(os.getenv("LLM_MODEL_ID") or "").strip(),
        llm_base_url=(os.getenv("LLM_BASE_URL") or "").strip(),
        llm_api_key=(os.getenv("LLM_API_KEY") or "").strip(),
        gemini_base_url=(
            os.getenv("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta"
        ).strip().rstrip("/"),
        gemini_api_key=(os.getenv("GEMINI_API_KEY") or "").strip(),
        openai_base_url=(os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().rstrip("/"),
        openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip(),
        embedding_model=(os.getenv("EMBEDDING_MODEL") or "all-MiniLM-L6-v2").strip(),
        rag_index_path=(os.getenv("RAG_INDEX_PATH") or "app/data/rag/index.faiss").strip(),
        rag_meta_path=(os.getenv("RAG_META_PATH") or "app/data/rag/meta.json").strip(),
        rag_top_k=int(os.getenv("RAG_TOP_K", "3")),
        mock_locked_status=(os.getenv("MOCK_LOCKED_STATUS", "false").lower() in {"1", "true", "yes"}),
    )
