# Java Testing tools MCP server

## example settings

```json
{
  "mcpServers": {
    "java_test_mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/java_test_mcp/",
        "run",
        "java_test_mcp"
      ],
      "disabled": false,
      "alwaysAllow": [],
      "description": "Java compilation and testing tools",
      "capabilities": {
        "tools": true
      },
      "env": {
        "CLIENT_WORKSPACE": "/path/to/vscode_project"
      }
    }
  }
}
```
