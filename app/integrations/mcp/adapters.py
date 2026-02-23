"""
MCP to OpenAI Adapters

Converts MCP tool schemas to OpenAI function calling format.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def mcp_tools_to_openai(mcp_tools: list) -> List[Dict[str, Any]]:
    """
    Convert MCP tool definitions to OpenAI function calling format.
    
    MCP tools have:
        - name: str
        - description: str
        - inputSchema: dict (JSON Schema)
    
    OpenAI expects:
        - type: "function"
        - function: {name, description, parameters}
    
    Security note: We strip 'user_id' from the parameters schema so the LLM
    cannot see or provide it. The MCPClientManager injects it automatically.
    
    Args:
        mcp_tools: List of MCP Tool objects
    
    Returns:
        List of OpenAI tool definitions
    """
    openai_tools = []

    for tool in mcp_tools:
        # Get the input schema from MCP tool
        input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}

        # Deep copy and strip user_id from schema
        # The LLM should NOT know about user_id — it's injected by the client
        parameters = _strip_user_id_from_schema(input_schema)

        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": parameters
            }
        }
        openai_tools.append(openai_tool)

    logger.debug(f"Converted {len(openai_tools)} MCP tools to OpenAI format")
    return openai_tools


def _strip_user_id_from_schema(schema: dict) -> dict:
    """
    Remove user_id from the JSON schema so the LLM never sees it.
    
    Args:
        schema: Original MCP inputSchema
    
    Returns:
        Modified schema without user_id property
    """
    if not schema or not isinstance(schema, dict):
        return schema

    result = dict(schema)

    # Remove user_id from properties
    properties = result.get("properties", {})
    if "user_id" in properties:
        properties = {k: v for k, v in properties.items() if k != "user_id"}
        result["properties"] = properties

    # Remove user_id from required list
    required = result.get("required", [])
    if "user_id" in required:
        result["required"] = [r for r in required if r != "user_id"]

    return result
