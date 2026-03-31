---
name: localvision
# A custom agent for working on the Local Picaso / LocalVision repository.
# This agent is intended to be selected when focusing on project-specific tasks,
# such as editing backend API logic, frontend UI, Docker setup, or data workflows.

description: |
  Use when you want an agent that is aware of the LocalVision project structure and
  aims to make safe, project-consistent changes across `backend/`, `frontend/`, and
  related configuration files. Prefer using local tools for reading and editing code.

# Apply this agent to these paths so it loads for requests involving the core app.
applyTo:
  - "backend/**"
  - "frontend/**"
  - "docker-compose.yml"
  - "*.md"

# Optional: add guidance about tool preferences and safe behavior.
# (Tool enforcement depends on the platform; keeping this here for human readers.)
notes: |
  - Prefer editing existing project files over creating new unrelated ones.
  - Avoid using external network calls or unrelated tooling.
  - Keep changes aligned with the existing FastAPI + SQLite backend and static frontend.
---
