import asyncio

from seed_data import MemoryStore, load_document
from server import McpSettings, build_server


def test_canonicalize_runs_on_the_server() -> None:
    settings = McpSettings(
        neo4j_uri="bolt://neo4j:7687",
        neo4j_user="neo4j",
        neo4j_password="skillproof-neo4j",
        mcp_token="test-mcp-token-0001",
    )
    server = build_server(MemoryStore(load_document()), settings)
    result = asyncio.run(server.call_tool("canonicalize_skill", {"text": "numpy"}))
    payload = result[1]
    assert payload["canonical"] == "NumPy"
    assert "Machine Learning" in payload["ancestors"]
