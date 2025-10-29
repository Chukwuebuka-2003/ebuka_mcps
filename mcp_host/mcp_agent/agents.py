from omnicoreagent import OmniAgent, MemoryRouter, EventRouter, logger
from utils.jwt_util import create_server_token
import asyncio
import os
from typing import Optional, Dict, Any


# Generate token dynamically
AUTH_TOKEN = create_server_token("tutoring-agent-mcp-client")

# Get RAG server URL from environment variable (Heroku) or use default (local Docker)
RAG_SERVER_URL = os.getenv("RAG_MCP_SERVER_URL", "http://rag_mcp_server:9000/mcp")

MCP_TOOLS = [
    {
        "name": "turtor_rag",
        "transport_type": "streamable_http",
        "url": RAG_SERVER_URL,
        "headers": {"Authorization": f"Bearer {AUTH_TOKEN}"},
    }
]


class TutoringRagAgent:
    def __init__(self):
        self.memory_router = None
        self.event_router = None
        self.agent = None
        self.mcp_client = None
        self.base_system_instruction = None
        self._agent_lock = asyncio.Lock()  # Prevent concurrent agent runs

    async def initialized(self):
        """Initialize the TutoringRagAgent server."""

        # Create memory and event routers
        self.memory_router = MemoryRouter(memory_store_type="redis")
        self.event_router = EventRouter(event_store_type="in_memory")

        # Import and store base system instruction
        from mcp_host.mcp_agent.system_prompt import base_system_instruction

        self.base_system_instruction = base_system_instruction

        # Create the OmniAgent with base instruction
        self.agent = OmniAgent(
            name="TutoringRagAgent",
            system_instruction=self.base_system_instruction,
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
                "request_limit": 0,
                "total_tokens_limit": 0,
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

        # Connect to MCP servers and log results
        logger.info("Connecting to MCP servers...")
        await self.agent.connect_mcp_servers()
        self.mcp_client = self.agent.mcp_client

        # Log available tools
        if hasattr(self.mcp_client, "sessions"):
            logger.info(f"MCP Sessions: {list(self.mcp_client.sessions.keys())}")
            for server_name, session_info in self.mcp_client.sessions.items():
                logger.info(
                    f"Server '{server_name}' tools: {session_info.get('tools', [])}"
                )

        logger.info("MCP servers connected successfully")

    async def handle_query(
        self,
        query: str,
        session_id: str = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Handle a user query and return the agent's response.

        Args:
            query: The user's question
            session_id: Session identifier for conversation continuity
            user_context: Dictionary containing user information (user_id, email, name)
        """
        # Acquire lock to prevent concurrent agent execution
        async with self._agent_lock:
            try:
                logger.info(f"Agent received query: {query[:100]}...")
                logger.info(f"Session ID: {session_id}")
                logger.info(f"User context: {user_context}")

                # ============= FIX: Inject user_id into system instruction =============
                if user_context and "user_id" in user_context:
                    user_id = user_context["user_id"]
                    logger.info(f"📝 Injecting user_id into system instruction: {user_id}")

                    # Create a modified system instruction with the actual user_id
                    modified_instruction = f"""{self.base_system_instruction}

<current_session_context>
🔑 CURRENT USER ID: {user_id}

CRITICAL: When calling knowledge_base_retrieval, you MUST use this EXACT user_id value:
user_id="{user_id}"

DO NOT use placeholder text. USE THE VALUE ABOVE.

Current user information:
- User ID: {user_id}
- Name: {user_context.get("name", "Unknown")}
- Email: {user_context.get("email", "Unknown")}
</current_session_context>
"""

                    # Update the agent's system instruction for this query
                    self.agent.system_instruction = modified_instruction
                    logger.info("✅ System instruction updated with user_id")
                else:
                    logger.warning("⚠️  No user context provided - using base instruction")
                # =======================================================================

                # Run the agent with timeout
                logger.info("Starting agent.run()...")
                result = await asyncio.wait_for(
                    self.agent.run(query, session_id), timeout=45.0
                )
                logger.info(f"Agent.run() completed")

                return result

            except asyncio.TimeoutError:
                logger.error("Agent.run() timed out after 45 seconds")
                return {
                    "response": "I apologize, but processing your request took too long. Please try a simpler question.",
                    "session_id": session_id or "timeout_session",
                }
            except Exception as e:
                logger.error(f"Failed to process query: {e}", exc_info=True)
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
            "memory_store_type": "redis",
            "memory_store_info": self.memory_router.get_memory_store_info(),
            "event_store_type": self.agent.get_event_store_type(),
            "debug_mode": self.agent.debug,
        }
