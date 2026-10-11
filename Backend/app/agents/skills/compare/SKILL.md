---
name: compare
description: Score one profile against several job descriptions with the skill graph.
tools:
  - skillgraph.score_match
inputs:
  - resume_skills
  - jd_skills
outputs:
  - ranked
limits:
  max_tool_calls: 12
  timeout_s: 60
---

Role: this file allows the compare route to call score_match. The ranking is code, not a model.
