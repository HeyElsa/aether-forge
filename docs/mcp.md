# Model Context Protocol (MCP) in Aether Forge

Aether Forge is an **MCP client**. Generated agents can discover and call tools from any MCP server — local subprocess, remote HTTP endpoint, or both at the same time — as part of their capability manifest at runtime.

This unlocks two interoperability stories:

1. **Consume external tools in Aether agents.** Filesystem servers, GitHub API servers, web search servers, and the `hermes mcp serve` bridge to 15+ messaging platforms all become available to your agents as regular capabilities.
2. **Bridge Aether Forge with other agent frameworks.** Hermes Agent from Nous Research exposes its messaging gateway as an MCP server via `hermes mcp serve`. Point Aether Forge at it and your generated trading/data agents can notify users on Telegram, Discord, Slack, WhatsApp, Signal, Matrix, and more — without Aether Forge maintaining any platform integrations itself.

Aether Forge does **not** yet expose itself as an MCP server. That's a planned follow-up.

---

## Quick start — local filesystem MCP server

```bash
# In one terminal: start a stdio filesystem MCP server
npx -y @modelcontextprotocol/server-filesystem /tmp
```

In your Aether Forge agent's `aether-forge.json`:

```json
{
  "planner": {
    "mode": "ollama",
    "model": "gemma4:latest",
    "baseUrl": "http://localhost:11434"
  },
  "runtime": {
    "cryptoRouter": "mock"
  },
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}
```

Then run the agent and the filesystem MCP tools will be discovered at runtime:

```bash
forge run ./my-agent --mode paper --auto-approve
```

`forge doctor ./my-agent/aether-forge.json` will probe the server and report how many tools it exposes.

---

## Quick start — Hermes Agent messaging bridge

First install and run Hermes Agent as an MCP server in one terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
hermes mcp serve    # exposes 10 messaging tools over stdio
```

Then in your Aether Forge agent's `aether-forge.json`:

```json
{
  "mcp_servers": {
    "hermes": {
      "command": "hermes",
      "args": ["mcp", "serve"]
    }
  }
}
```

Your generated agent can now call tools like `messages_send`, `messages_list`, etc. from Hermes Agent. The agent's planner will see these as declared capabilities and can use them to notify you on Telegram, Discord, Slack, or any platform Hermes Agent's gateway is configured for.

---

## Quick start — remote HTTP MCP server

```json
{
  "mcp_servers": {
    "example_api": {
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${EXAMPLE_API_TOKEN}"
      }
    }
  }
}
```

HTTP transport uses streamable-HTTP request/response. Aether Forge's client implements the plain request/response shape, not the full SSE streaming protocol — good enough for most server-exposed REST-style MCP endpoints.

---

## Tool filtering

MCP servers often expose more tools than you want any given agent to touch. You can whitelist or blacklist per server:

```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GH_TOKEN}"
      },
      "tools": {
        "include": ["list_issues", "create_issue", "search_repositories"],
        "exclude": ["delete_repository"]
      }
    }
  }
}
```

- `tools.include` — if present, only these tools are exposed to the agent. Acts as a whitelist.
- `tools.exclude` — tools to filter out even if they'd otherwise be included.

Apply both when you need to scope a single server to a specific agent's needs without maintaining a forked version of the server.

---

## Security

### Stdio subprocess hardening

When Aether Forge spawns an MCP server as a subprocess, it does **not** leak the full parent environment to the child. Only a safe baseline (`PATH`, `HOME`, `USER`, `SHELL`, `LANG`, `LC_ALL`, `TERM`) plus whatever you explicitly declare in `env:` is passed through. This matches Hermes Agent's own stdio hardening behavior.

### Credentials in env vars

Never put secrets directly in `aether-forge.json`. Use env vars:

```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GH_TOKEN}"
      }
    }
  }
}
```

Then set `GH_TOKEN` in your shell or in the agent's `.env` file (which is already gitignored and locked to `0600` by the framework's security hardening).

### Halt file blocks MCP tool calls from live mode

When the agent runs in live mode and the `halt` file is present, all side-effecting MCP tool calls are blocked along with the existing x402 payment checks. The kill switch is global across every channel an agent can touch the outside world through.

---

## Programmatic API

If you're embedding Aether Forge in your own Python code, the MCP client is directly usable:

```python
from aether_forge.mcp_client import McpServerConfig, McpStdioClient

config = McpServerConfig(
    name="filesystem",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
)

with McpStdioClient(config) as client:
    tools = client.list_tools()
    for tool in tools:
        print(tool["name"], tool.get("description", ""))

    result = client.call_tool("read_file", {"path": "/tmp/test.txt"})
    print(result)
```

Or wrap it as a data source for the `DataRouter`:

```python
from aether_forge.data_layer import build_mcp_source, DataRouter

hermes_mcp = build_mcp_source(
    {"command": "hermes", "args": ["mcp", "serve"]},
    name="hermes",
)

router = DataRouter([hermes_mcp])
result = router.fetch("messages_send", platform="telegram", text="Hello from Aether Forge")
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `forge doctor` reports `MCP server [X] Unreachable` | Server isn't installed or the command isn't on `PATH` | Install the server (`npm i -g`, etc.) and verify with `which <command>` |
| Stdio server exits immediately | Missing env var, wrong args | Check the server's own docs; pass required env through the `env:` block |
| `McpProtocolError: method not found` | Server doesn't support `tools/list` or `tools/call` | Probably a non-MCP-compliant or resources-only server. Not compatible yet. |
| Tool calls hang | Slow server or network timeout | Bump `timeout_seconds` in the server config; default is 30s |
| `call_tool` returns structured content you can't parse | MCP spec allows arbitrary `content` arrays | Check the tool's `inputSchema` / `outputSchema` and parse accordingly |
| Server works with Claude Code but not Aether Forge | You hit a spec corner we don't implement yet (resources, prompts, streaming) | File an issue; core ops (`tools/list`, `tools/call`) are all that's supported currently |

---

## What's not supported yet

- **Resources** (`resources/list`, `resources/read`) — MCP has a concept of static resources separate from tools. Aether Forge only implements the tools API.
- **Prompts** (`prompts/list`, `prompts/get`) — Reusable prompt templates exposed by MCP servers. Not yet wired into the planner.
- **Sampling** — MCP servers can ask the client to run an LLM completion on their behalf. Not implemented.
- **Subscriptions / streaming** — SSE-based streaming transport is not implemented. Only request/response HTTP works.
- **Aether Forge as an MCP server** — `forge mcp serve` to expose Aether-generated agents as MCP tools is planned but not shipped yet.

If any of the above becomes a blocker for your use case, the smallest unit of work needed is usually ~100 lines in `mcp_client.py`. Pull requests welcome.

---

## Reference

- Protocol specification: https://modelcontextprotocol.io/
- Official server registry: https://github.com/modelcontextprotocol/servers
- Hermes Agent (runs `hermes mcp serve`): https://hermes-agent.nousresearch.com/
