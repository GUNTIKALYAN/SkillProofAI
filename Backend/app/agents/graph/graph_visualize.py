from pathlib import Path
from app.agents.graph.graph_builder import build_skillproof_graph

graph = build_skillproof_graph()

png_bytes = graph.get_graph().draw_mermaid_png()

# Save directly inside app/agents/graph/
output_path = Path(__file__).parent / "skillproofai_agent_flow.png"

with open(output_path, "wb") as f:
    f.write(png_bytes)

print(f"✅ Graph saved at {output_path}")
