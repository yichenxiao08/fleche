# FenceCoach MCP

The local stdio server exposes five read-only tools:

1. `get_session_measurements`
2. `list_reps`
3. `compare_to_baseline`
4. `get_practice_history`
5. `search_coaching_library`

Read `fencecoach://sessions` to discover IDs. Video sessions must pass the same QA gate used by the app. Synthetic sessions are explicitly marked. Comparisons require confirmed, matching named camera setups.

Example client configuration (replace every path with your absolute project path):

```json
{
  "mcpServers": {
    "fencecoach": {
      "command": "C:/path/to/fencecoach/.venv/Scripts/python.exe",
      "args": ["-m", "fencecoach.mcp_server"],
      "env": {
        "FENCECOACH_DB_PATH": "C:/path/to/fencecoach/data/fencecoach.sqlite3",
        "FENCECOACH_VIDEO_DIR": "C:/path/to/fencecoach/data/videos",
        "FENCECOACH_KNOWLEDGE_DIR": "C:/path/to/fencecoach/knowledge"
      }
    }
  }
}
```

The client controls its model and instructions; a read-only tool cannot force a third-party model to make a justified correction. Keep the measurement limitations in the assistant's instructions.

Run `python scripts/mcp_smoke.py` to exercise initialization, discovery, resource reads, all five calls, and missing-session errors through a real subprocess using the official SDK. This check passed locally. Claude Desktop and Claude Code are not installed/authenticated here, so that client integration remains unverified.

Reference: [official Python MCP SDK v1](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).
