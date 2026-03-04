"""
MCP Client Manager — Multi-Server Registry

Manages connections to multiple MCP servers (BigQuery, Highcharts, etc.).
Provides unified tool discovery and execution with automatic user_id injection.
Routes tool calls to the correct server via an auto-built tool→server mapping.
"""

import logging
from typing import Any, Dict, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings

logger = logging.getLogger(__name__)


class _MCPServerConnection:
    """Manages a single MCP server connection."""

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self._session: Optional[ClientSession] = None
        self._tools: Optional[list] = None
        self._context_manager = None
        self._streams = None
        # Tracks which tools require user_id in their original schema
        self.tools_requiring_user_id: set = set()

    async def connect(self) -> None:
        if self._session is not None:
            return
        try:
            logger.info(f"Connecting to MCP Server '{self.name}' at {self.url}")
            self._context_manager = streamablehttp_client(url=self.url)
            self._streams = await self._context_manager.__aenter__()

            read_stream, write_stream, _ = self._streams
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools

            # Detect which tools have user_id in their schema
            for tool in self._tools:
                schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
                props = schema.get("properties", {}) if isinstance(schema, dict) else {}
                if "user_id" in props:
                    self.tools_requiring_user_id.add(tool.name)

            tool_names = [t.name for t in self._tools]
            logger.info(f"MCP '{self.name}' connected. Tools: {tool_names}")

        except Exception as e:
            logger.error(f"Failed to connect to MCP Server '{self.name}': {e}")
            self._session = None
            self._tools = None
            raise

    async def disconnect(self) -> None:
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._context_manager:
                await self._context_manager.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error during MCP '{self.name}' disconnect: {e}")
        finally:
            self._session = None
            self._tools = None
            self._context_manager = None
            self._streams = None
            logger.info(f"MCP '{self.name}' session disconnected")

    async def reconnect(self) -> None:
        logger.info(f"MCP '{self.name}' session appears stale — forcing reconnect")
        await self.disconnect()
        await self.connect()

    async def list_tools(self) -> list:
        if self._session is None:
            await self.connect()
        if self._tools is None:
            try:
                tools_result = await self._session.list_tools()
                self._tools = tools_result.tools
            except Exception:
                await self.reconnect()
                tools_result = await self._session.list_tools()
                self._tools = tools_result.tools
        return self._tools

    async def call_tool(self, name: str, args: dict) -> str:
        if self._session is None:
            await self.connect()
        try:
            result = await self._session.call_tool(name, args)
            return self._extract_text(result)
        except Exception as e:
            logger.warning(
                f"MCP '{self.name}' tool call '{name}' failed "
                f"({type(e).__name__}: {e}), reconnecting and retrying..."
            )
            await self.disconnect()
            await self.connect()
            result = await self._session.call_tool(name, args)
            return self._extract_text(result)

    @staticmethod
    def _extract_text(result) -> str:
        if result.content:
            text_parts = [
                part.text for part in result.content
                if hasattr(part, "text")
            ]
            return "\n".join(text_parts)
        return "{}"


class MCPClientManager:
    """
    Singleton registry for multiple MCP server connections.

    Handles:
    - Connection lifecycle to all registered MCP servers
    - Unified tool discovery (merges tools from all servers)
    - Automatic tool → server routing
    - Tool execution with selective user_id injection
    - Reconnection on failure
    """

    _instance: Optional["MCPClientManager"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if MCPClientManager._initialized:
            return

        # Build server registry from settings
        self._servers: Dict[str, _MCPServerConnection] = {}
        self._tool_to_server: Dict[str, str] = {}  # tool_name → server_name
        self._all_tools: Optional[list] = None

        # Always register BigQuery server (backward-compatible)
        self._register_server("bigquery", settings.MCP_BIGQUERY_SERVER_URL)

        # Register Highcharts server if configured
        highcharts_url = getattr(settings, "MCP_HIGHCHARTS_SERVER_URL", None)
        if highcharts_url:
            self._register_server("highcharts", highcharts_url)

        MCPClientManager._initialized = True
        logger.info(
            f"MCPClientManager initialized with {len(self._servers)} server(s): "
            f"{list(self._servers.keys())}"
        )

    def _register_server(self, name: str, url: str) -> None:
        """Register a new MCP server connection."""
        self._servers[name] = _MCPServerConnection(name, url)
        logger.info(f"Registered MCP server '{name}' at {url}")

    async def connect(self) -> None:
        """Connect to all registered MCP servers and build tool routing map.
        
        Individual server failures are logged but don't prevent other servers
        from connecting. This ensures BigQuery tools remain available even if
        the Highcharts server is down.
        """
        for name, server in self._servers.items():
            try:
                await server.connect()
            except Exception as e:
                logger.warning(
                    f"MCP server '{name}' failed to connect: {e}. "
                    f"Its tools will not be available."
                )
        await self._build_tool_map()

    async def disconnect(self) -> None:
        """Disconnect all MCP servers."""
        for server in self._servers.values():
            await server.disconnect()
        self._tool_to_server.clear()
        self._all_tools = None
        logger.info("All MCP sessions disconnected")

    async def _ensure_connected(self) -> None:
        """Ensure all servers are connected (best-effort per server)."""
        for name, server in self._servers.items():
            if server._session is None:
                try:
                    await server.connect()
                except Exception as e:
                    logger.warning(
                        f"MCP server '{name}' reconnection failed: {e}. "
                        f"Its tools will not be available."
                    )
        if not self._tool_to_server:
            await self._build_tool_map()

    async def _build_tool_map(self) -> None:
        """Build the tool_name → server_name routing map from all connected servers."""
        self._tool_to_server.clear()
        all_tools = []
        for server_name, server in self._servers.items():
            if server._session is None:
                logger.warning(f"Skipping tool map for '{server_name}' — not connected")
                continue
            try:
                tools = await server.list_tools()
            except Exception as e:
                logger.warning(f"Failed to list tools from '{server_name}': {e}")
                continue
            for tool in tools:
                if tool.name in self._tool_to_server:
                    logger.warning(
                        f"Tool name collision: '{tool.name}' exists in both "
                        f"'{self._tool_to_server[tool.name]}' and '{server_name}'. "
                        f"Using '{server_name}'."
                    )
                self._tool_to_server[tool.name] = server_name
                all_tools.append(tool)
        self._all_tools = all_tools
        logger.info(
            f"Tool routing map built: {len(self._tool_to_server)} tools across "
            f"{len(self._servers)} servers"
        )

    def tool_requires_user_id(self, tool_name: str) -> bool:
        """Check if a tool requires user_id injection (based on its original schema)."""
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            return True  # Default to injecting for safety
        server = self._servers[server_name]
        return tool_name in server.tools_requiring_user_id

    async def list_tools(self) -> list:
        """
        Get all available tools from all MCP servers.

        Returns:
            Merged list of MCP Tool objects from all registered servers.
        """
        await self._ensure_connected()
        if self._all_tools is None:
            await self._build_tool_map()
        return self._all_tools

    async def call_tool(
        self,
        name: str,
        args: Dict[str, Any],
        user_id: str,
    ) -> str:
        """
        Execute an MCP tool, routing to the correct server automatically.

        user_id is injected only for tools that require it in their schema.
        The LLM never provides or sees user_id.

        Args:
            name: Tool name (e.g., 'tool_get_report_blocks', 'tool_build_chart')
            args: Arguments from OpenAI tool_call
            user_id: User ID from JWT (injected, NOT from LLM)

        Returns:
            Tool result as string (JSON)
        """
        await self._ensure_connected()

        server_name = self._tool_to_server.get(name)
        if not server_name:
            logger.error(f"No server found for tool '{name}'. Known tools: {list(self._tool_to_server.keys())}")
            return '{"error": "Unknown tool: ' + name + '"}'

        server = self._servers[server_name]

        # Inject user_id only if the tool requires it
        if self.tool_requires_user_id(name):
            final_args = {**args, "user_id": user_id}
        else:
            final_args = dict(args)

        logger.info(f"Calling MCP tool: {name} on server '{server_name}' with args: {list(final_args.keys())}")
        response = await server.call_tool(name, final_args)
        logger.info(f"MCP tool {name} returned {len(response)} chars")
        return response
