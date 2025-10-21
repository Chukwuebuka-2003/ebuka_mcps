from omnicoreagent import OmniAgent, MemoryRouter, EventRouter, logger
from mcp_host.mcp_agent.system_prompt import system_instruction


MCP_TOOLS = [
    {
        "name": "turtor_rag",
        "transport_type": "streamable_http",
        "url": "http://0.0.0.0:9000/mcp",
        "headers": {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJteS1zZXJ2ZXItMDEiLCJleHAiOjE3NjEwNzg4MTAsImlhdCI6MTc2MDcxODgxMH0.Y6aWWx9-uy1S4LprE6mDwUzj-py8E1FnN7QHmWHHhpY"
        },
    }
]


class TutoringRagAgent:
    async def initialized(self):
        """Initialize the TutoringRagAgent server."""

        # Create memory and event routers
        self.memory_router = MemoryRouter(memory_store_type="redis")
        self.event_router = EventRouter(event_store_type="in_memory")

        # Create the OmniAgent
        self.agent = OmniAgent(
            name="TutoringRagAgent",
            system_instruction=system_instruction,
            model_config={
                "provider": "openai",
                "model": "gpt-4.1",
                "temperature": 0.3,
                "max_context_length": 5000,
                "top_p": 0.7,
            },
            mcp_tools=MCP_TOOLS,
            agent_config={
                "agent_name": "TutoringRagAgent",
                "max_steps": 15,
                "tool_call_timeout": 60,
                "request_limit": 0,  # 0 = unlimited
                "total_tokens_limit": 0,  # or 0 for unlimited
                # --- Memory Retrieval Config ---
                "memory_config": {"mode": "sliding_window", "value": 100},
                "memory_results_limit": 5,
                "memory_similarity_threshold": 0.5,
                # --- Tool Retrieval Config ---
                "enable_tools_knowledge_base": False,
                "tools_results_limit": 10,
                "tools_similarity_threshold": 0.1,
                "memory_tool_backend": "local",
            },
            memory_router=self.memory_router,
            event_router=self.event_router,
            debug=True,
        )
        await self.agent.connect_mcp_servers()
        self.mcp_client = self.agent.mcp_client

    async def handle_query(self, query: str, session_id: str = None) -> dict:
        """Handle a user query and return the agent's response.

        Args:
            query: User's query/message
            session_id: Optional session ID for conversation continuity

        Returns:
            Dict with response and session_id
        """
        try:
            # Run the agent
            result = await self.agent.run(query, session_id)
            return result

        except Exception as e:
            logger.error(f"Failed to process query: {e}")
            return {
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "session_id": session_id or "error_session",
            }

    async def get_session_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session."""
        try:
            return await self.agent.get_session_history(session_id)
        except Exception as e:
            logger.error(f"Failed to get session history: {e}")
            return []

    async def clear_session_memory(self, session_id: str) -> bool:
        """Clear memory for a specific session."""
        try:
            await self.agent.clear_session_history(session_id)
            logger.info(f"Cleared memory for session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear session memory: {e}")
            return False

    def get_agent_info(self) -> dict:
        """Get information about the agent configuration."""
        return {
            "agent_name": self.agent.name,
            "memory_store_type": "in_memory",
            "memory_store_info": self.memory_router.get_memory_store_info(),
            "event_store_type": self.agent.get_event_store_type(),
            "debug_mode": self.agent.debug,
        }
