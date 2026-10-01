import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

LLAMA_MODEL = "openai/gpt-oss-20b"

SEMANTIC_MODEL_NAME = os.getenv("SEMANTIC_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
SEMANTIC_MATCH_THRESHOLD = float(os.getenv("SEMANTIC_THRESHOLD", "0.55"))

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set")
