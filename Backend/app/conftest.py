import os

# config.py refuses to import when this is missing. CI and local pytest
# set a dummy value here so collection can finish without a real Groq key.
os.environ.setdefault("GROQ_API_KEY", "test_dummy_key")
