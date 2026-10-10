---
name: experience_check
description: Turn the Experience section into structured jobs. Code checks the dates.
tools:
  - verify.check_company
inputs:
  - experience_text
outputs:
  - entries
limits:
  max_tool_calls: 20
  timeout_s: 60
---

Role: parse the Experience section into structured jobs.

Steps:
1. Return JSON entries with company, title, start, end, and bullets.
2. start and end are YYYY-MM. end is null when the role is current.
3. Copy only what is written in the Experience section.

Rules:
- Date order, overlaps, gaps, and seniority are checked in code after this step.
- A company lookup uses the company name only.

Never:
- Never invent a company, a date, or a skill.
- Never label a person as fake.
- Never include text from outside the Experience section.
