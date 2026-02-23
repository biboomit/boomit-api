"""
MCP Client Manager

Manages connection to the MCP BigQuery Server.
Provides tool discovery and execution with automatic user_id injection.
"""

import logging
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    Singleton manager for MCP Server connection.
    
    Handles:
    - Connection lifecycle to MCP BigQuery Server
    - Tool discovery (list_tools)
    - Tool execution with automatic user_id injection
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
        
        self.server_url: str = settings.MCP_BIGQUERY_SERVER_URL
        self._session: Optional[ClientSession] = None
        self._tools: Optional[list] = None
        self._context_manager = None
        self._streams = None

        MCPClientManager._initialized = True
        logger.info(f"MCPClientManager initialized with server URL: {self.server_url}")

    async def connect(self) -> None:
        """Establish connection to MCP Server"""
        if self._session is not None:
            logger.debug("MCP session already connected")
            return

        try:
            logger.info(f"Connecting to MCP Server at {self.server_url}")
            self._context_manager = streamablehttp_client(url=self.server_url)
            self._streams = await self._context_manager.__aenter__()
            
            read_stream, write_stream, _ = self._streams
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            # Cache available tools
            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools
            
            tool_names = [t.name for t in self._tools]
            logger.info(f"MCP connected. Available tools: {tool_names}")

        except Exception as e:
            logger.error(f"Failed to connect to MCP Server: {e}")
            self._session = None
            self._tools = None
            raise

    async def disconnect(self) -> None:
        """Close connection to MCP Server"""
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._context_manager:
                await self._context_manager.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error during MCP disconnect: {e}")
        finally:
            self._session = None
            self._tools = None
            self._context_manager = None
            self._streams = None
            logger.info("MCP session disconnected")

    async def _ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed"""
        if self._session is None:
            await self.connect()

    async def _reconnect(self) -> None:
        """Force disconnect then reconnect (used after a stale/closed session is detected)"""
        logger.info("MCP session appears stale — forcing reconnect")
        await self.disconnect()
        await self.connect()

    async def list_tools(self) -> list:
        """
        Get available tools from the MCP Server.
        
        Returns:
            List of MCP Tool objects with name, description, and inputSchema
        """
        await self._ensure_connected()
        if self._tools is None:
            try:
                tools_result = await self._session.list_tools()
                self._tools = tools_result.tools
            except Exception as e:
                logger.warning(f"list_tools failed ({type(e).__name__}: {e}), reconnecting...")
                await self._reconnect()
                tools_result = await self._session.list_tools()
                self._tools = tools_result.tools
        return self._tools

    async def call_tool(
        self,
        name: str,
        args: Dict[str, Any],
        user_id: str
    ) -> str:
        """
        Execute an MCP tool with automatic user_id injection.
        
        The user_id is injected from the JWT session context — the LLM
        never provides or sees the user_id. This ensures ownership
        validation on every tool call.
        
        Args:
            name: Tool name (e.g., 'tool_get_report_blocks')
            args: Arguments from OpenAI tool_call (report_id, block_key, etc.)
            user_id: User ID from JWT (injected, NOT from LLM)
        
        Returns:
            Tool result as string (JSON)
        """
        await self._ensure_connected()

        # Inject user_id — security: LLM cannot override this
        args_with_user = {**args, "user_id": user_id}

        logger.info(f"Calling MCP tool: {name} with args: {list(args_with_user.keys())}")

        try:
            result = await self._session.call_tool(name, args_with_user)
            
            # Extract text content from MCP result
            if result.content:
                text_parts = [
                    part.text for part in result.content
                    if hasattr(part, "text")
                ]
                response = "\n".join(text_parts)
            else:
                response = "{}"

            logger.info(f"MCP tool {name} returned {len(response)} chars")
            return response

        except Exception as e:
            logger.warning(f"MCP tool call failed ({type(e).__name__}: {e}), reconnecting and retrying...")
            # Disconnect so next call (or the retry below) gets a fresh session
            await self.disconnect()
            # Retry once after reconnect
            await self.connect()
            result = await self._session.call_tool(name, args_with_user)
            if result.content:
                text_parts = [
                    part.text for part in result.content
                    if hasattr(part, "text")
                ]
                return "\n".join(text_parts)
            return "{}"
