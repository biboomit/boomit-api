"""
MCP Chat Host

Orchestrates OpenAI + MCP tools for the marketing chat.
Implements the tool-calling loop: OpenAI ↔ MCP Server.
Yields SSE tokens compatible with the existing frontend format.
"""

import json
import logging
from typing import AsyncGenerator, Dict, Any, List

from openai import AsyncOpenAI

from app.core.config import settings
from app.integrations.mcp.client import MCPClientManager
from app.integrations.mcp.adapters import mcp_tools_to_openai
from app.core.exceptions import BoomitAPIException

logger = logging.getLogger(__name__)


class MCPChatHost:
    """
    Combines AsyncOpenAI client with MCP tools for marketing chat.
    
    Flow:
    1. Send messages + tools to OpenAI
    2. If OpenAI responds with tool_calls → execute via MCP Client
    3. Add tool results to messages
    4. Re-send to OpenAI → repeat until final text response
    5. Stream final response tokens via SSE
    
    Security:
    - user_id is injected by MCPClientManager, never sent by OpenAI/LLM
    - Max tool rounds prevent infinite loops
    """

    def __init__(self):
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini")
        self.mcp_client = MCPClientManager()
        self.max_tool_rounds = settings.MCP_MAX_TOOL_ROUNDS
        self._openai_tools = None

        logger.info(
            f"MCPChatHost initialized: model={self.model}, "
            f"max_tool_rounds={self.max_tool_rounds}"
        )

    async def _get_openai_tools(self) -> list:
        """Get tools in OpenAI format (cached after first call)"""
        if self._openai_tools is None:
            mcp_tools = await self.mcp_client.list_tools()
            self._openai_tools = mcp_tools_to_openai(mcp_tools)
            logger.info(f"Loaded {len(self._openai_tools)} tools for OpenAI")
        return self._openai_tools

    async def _execute_tool_calls(
        self,
        tool_calls: list,
        user_id: str
    ) -> List[Dict[str, str]]:
        """
        Execute MCP tool calls requested by OpenAI.
        
        Args:
            tool_calls: List of tool_call objects from OpenAI response
            user_id: User ID from JWT (injected into every tool call)
        
        Returns:
            List of tool result messages for OpenAI
        """
        tool_messages = []

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                function_args = {}

            logger.info(
                f"Executing tool: {function_name} "
                f"(args: {list(function_args.keys())})"
            )

            try:
                result = await self.mcp_client.call_tool(
                    name=function_name,
                    args=function_args,
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Tool execution failed: {function_name} - {e}")
                result = json.dumps({
                    "error": f"Tool execution failed: {str(e)}"
                })

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

        return tool_messages

    async def stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        user_id: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream AI response with MCP tool calling support.
        
        Handles the full tool-calling loop:
        - If OpenAI needs data → calls MCP tools → feeds results back
        - Once OpenAI is ready to respond → streams tokens
        
        Yields tokens in the same format as the original MarketingChatService.stream_response(),
        maintaining full compatibility with the frontend SSE consumer.
        
        Args:
            messages: Prepared messages (system prompt + history + user message)
            user_id: User ID from JWT for tool call ownership validation
        
        Yields:
            Response text tokens as they arrive
        """
        try:
            tools = await self._get_openai_tools()
        except Exception as e:
            logger.error(f"Failed to load MCP tools: {type(e).__name__}: {e}", exc_info=True)
            self._openai_tools = None  # reset cache so next call re-fetches after reconnect
            raise BoomitAPIException(
                message="Failed to connect to MCP tools",
                status_code=500,
                error_code="MCP_TOOLS_LOAD_ERROR",
                details={"error": repr(e)}
            )

        current_messages = list(messages)
        rounds = 0

        while rounds < self.max_tool_rounds:
            rounds += 1
            logger.info(f"Tool-calling round {rounds}/{self.max_tool_rounds}")

            try:
                # Call OpenAI with tools — NON-streaming first to check for tool_calls
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=current_messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=1500
                )

                choice = response.choices[0]
                message = choice.message

                # If OpenAI wants to call tools
                if message.tool_calls:
                    logger.info(
                        f"OpenAI requested {len(message.tool_calls)} tool call(s): "
                        f"{[tc.function.name for tc in message.tool_calls]}"
                    )

                    # Add assistant message with tool_calls to history
                    current_messages.append({
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in message.tool_calls
                        ]
                    })

                    # Execute tools and add results
                    tool_results = await self._execute_tool_calls(
                        message.tool_calls, user_id
                    )
                    current_messages.extend(tool_results)

                    # Continue loop — OpenAI will process tool results
                    continue

                # No tool calls — OpenAI has a final response
                # Now re-call with streaming for token-by-token delivery
                logger.info("OpenAI ready to respond — streaming final response")

                stream = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=current_messages,
                    tools=tools,
                    tool_choice="none",  # Force text response, no more tools
                    stream=True,
                    temperature=0.2,
                    max_tokens=1500
                )

                async for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content

                logger.info(f"Streaming completed after {rounds} round(s)")
                return

            except BoomitAPIException:
                raise
            except Exception as e:
                logger.error(f"Error in tool-calling round {rounds}: {type(e).__name__}: {e}", exc_info=True)
                raise BoomitAPIException(
                    message="Failed to generate AI response",
                    status_code=500,
                    error_code="MCP_AI_GENERATION_ERROR",
                    details={"error": repr(e), "round": rounds}
                )

        # Max rounds exceeded — force a final response without tools
        logger.warning(f"Max tool rounds ({self.max_tool_rounds}) exceeded, forcing response")
        try:
            stream = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=current_messages,
                stream=True,
                temperature=0.2,
                max_tokens=1500
            )
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Final fallback streaming failed: {type(e).__name__}: {e}", exc_info=True)
            raise BoomitAPIException(
                message="Failed to generate AI response after max tool rounds",
                status_code=500,
                error_code="MCP_MAX_ROUNDS_ERROR",
                details={"error": repr(e)}
            )
