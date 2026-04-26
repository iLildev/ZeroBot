"""Builder Agent — autonomous coding agent core for ZeroBot.

Components:
    - sandbox.py        : per-user isolated workspace + safe shell/file ops
    - tools.py          : Anthropic tool schemas + dispatcher
    - llm.py            : Claude client (via Replit AI Integrations proxy)
    - builder_agent.py  : the agent loop (Claude + tools + iteration)
    - cli_test.py       : interactive REPL for testing without Telegram
"""
