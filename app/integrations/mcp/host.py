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
    ) -> AsyncGenerator[Any, None]:
        """
        Stream AI response with MCP tool calling support.
        
        Handles the full tool-calling loop:
        - If OpenAI needs data → calls MCP tools → feeds results back
        - Once OpenAI is ready to respond → streams tokens
        
        Yields tokens in the same format as the original MarketingChatService.stream_response(),
        maintaining full compatibility with the frontend SSE consumer.
        Yields a final {"__type": "usage", ...} dict with accumulated token usage.
        
        Args:
            messages: Prepared messages (system prompt + history + user message)
            user_id: User ID from JWT for tool call ownership validation
        
        Yields:
            Response text tokens, then a usage stats dict as the last item
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
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tool_calls = 0
        llm_calls_count = 0

        for round_num in range(1, self.max_tool_rounds + 2):
            is_forced_final = round_num > self.max_tool_rounds
            if is_forced_final:
                logger.warning(f"Max tool rounds ({self.max_tool_rounds}) exceeded, forcing final response")
            else:
                logger.info(f"Tool-calling round {round_num}/{self.max_tool_rounds}")

            try:
                # Every round is streaming — collect tool_calls or yield text directly
                call_kwargs = dict(
                    model=self.model,
                    messages=current_messages,
                    tools=tools,
                    tool_choice="none" if is_forced_final else "auto",
                    stream=True,
                    temperature=0.2,
                    max_tokens=1500,
                    stream_options={"include_usage": True},
                )

                stream = await self.openai_client.chat.completions.create(**call_kwargs)
                llm_calls_count += 1

                # Collect streamed response — tool_call fragments and/or text tokens
                collected_tool_calls: Dict[int, Dict] = {}
                content_tokens: List[str] = []

                async for chunk in stream:
                    if chunk.usage:
                        total_prompt_tokens += chunk.usage.prompt_tokens
                        total_completion_tokens += chunk.usage.completion_tokens

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # Accumulate tool_call fragments by index
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in collected_tool_calls:
                                collected_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                            entry = collected_tool_calls[idx]
                            if tc_delta.id:
                                entry["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    entry["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    entry["arguments"] += tc_delta.function.arguments

                    # Buffer content tokens
                    if delta.content:
                        content_tokens.append(delta.content)

                if collected_tool_calls and not is_forced_final:
                    # ── TOOL ROUND: execute tools, append results, continue loop ──
                    tool_calls_list = [
                        {
                            "id": entry["id"],
                            "type": "function",
                            "function": {"name": entry["name"], "arguments": entry["arguments"]},
                        }
                        for entry in (collected_tool_calls[i] for i in sorted(collected_tool_calls))
                    ]

                    assistant_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": "".join(content_tokens),
                        "tool_calls": tool_calls_list,
                    }
                    current_messages.append(assistant_msg)

                    logger.info(
                        f"OpenAI requested {len(tool_calls_list)} tool call(s): "
                        f"{[tc['function']['name'] for tc in tool_calls_list]}"
                    )

                    # Build lightweight objects for _execute_tool_calls
                    class _TC:
                        def __init__(self, d: Dict):
                            self.id = d["id"]
                            self.function = type("F", (), {
                                "name": d["function"]["name"],
                                "arguments": d["function"]["arguments"],
                            })()

                    tool_results = await self._execute_tool_calls(
                        [_TC(tc) for tc in tool_calls_list], user_id
                    )
                    total_tool_calls += len(tool_results)
                    current_messages.extend(tool_results)
                    continue  # next round

                else:
                    # ── FINAL TEXT ROUND: yield buffered tokens directly ──
                    logger.info(
                        f"OpenAI ready to respond — yielding {len(content_tokens)} tokens "
                        f"(round {round_num}, no extra LLM call needed)"
                    )
                    for token in content_tokens:
                        yield token
                    break

            except BoomitAPIException:
                raise
            except Exception as e:
                logger.error(
                    f"Error in round {round_num}: {type(e).__name__}: {e}", exc_info=True
                )
                raise BoomitAPIException(
                    message="Failed to generate AI response",
                    status_code=500,
                    error_code="MCP_AI_GENERATION_ERROR",
                    details={"error": repr(e), "round": round_num}
                )

        yield {
            "__type": "usage",
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "tool_calls_count": total_tool_calls,
            "llm_calls_count": llm_calls_count,
        }
