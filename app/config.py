import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI") or "postgresql+asyncpg://user:password@localhost:5432/ai_brain"
PGVECTOR_URI = os.getenv("PGVECTOR_URI") or DATABASE_URL

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

AI_ASSISTANT_SECRET = os.getenv("AI_ASSISTANT_SECRET", "")
if not AI_ASSISTANT_SECRET:
    raise ValueError(
        "AI_ASSISTANT_SECRET is not set. Set it in the environment before starting the brain."
    )

# Comma-separated list of origins allowed to call the brain from the browser
# (e.g. the Odoo frontend). If not set, all origins are allowed for backwards
# compatibility, but production deployments should set this explicitly.
_cors_origins = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [origin.strip() for origin in _cors_origins.split(",") if origin.strip()] or ["*"]

# Maximum cosine distance for a snippet/document/fact to be considered relevant.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.4"))
