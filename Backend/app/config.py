import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

LLAMA_MODEL = "llama-3.1-8b-instant"

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set")
