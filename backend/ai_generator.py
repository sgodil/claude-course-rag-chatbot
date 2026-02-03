import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    MAX_TOOL_ROUNDS = 2

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to tools for course information.

Tool Usage:
- `search_course_content` — Search course content for questions about specific topics, lessons, or detailed educational materials
- `get_course_outline` — Retrieve a course's full outline (title, course link, and numbered lesson list) for questions about a course's syllabus, structure, or what lessons it contains
- You may use up to 2 tools sequentially when needed (e.g., `get_course_outline` first to identify a lesson, then `search_course_content` to get details)
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without using tools
- **Course-specific questions**: Use the appropriate tool first, then answer
- **Outline/syllabus/lesson-list questions**: Use `get_course_outline`
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text from the first text block in a response."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Uses an agentic loop that allows up to MAX_TOOL_ROUNDS sequential tool
        calls before forcing a final text response.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        messages = [{"role": "user", "content": query}]
        response = None

        for round in range(self.MAX_TOOL_ROUNDS):
            api_params = {
                **self.base_params,
                "messages": messages,
                "system": system_content
            }

            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = {"type": "auto"}

            response = self.client.messages.create(**api_params)

            if response.stop_reason != "tool_use" or not tool_manager:
                break

            # Append assistant message with tool use blocks
            messages.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_result = tool_manager.execute_tool(
                        block.name,
                        **block.input
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result
                    })

            # Append tool results as user message
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        # If loop exhausted and last response was still tool_use, force a text response
        if response.stop_reason == "tool_use":
            api_params = {
                **self.base_params,
                "messages": messages,
                "system": system_content
            }
            response = self.client.messages.create(**api_params)

        return self._extract_text(response)
