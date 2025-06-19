import asyncio
import os
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import SseServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_core import CancellationToken
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=True)

    # Create server params for the remote MCP service
    server_params = SseServerParams(
        url=os.getenv("SERVER_URL", default=f"{os.getenv('MCP_ENPOINT', default='http://localhost:8080')}/sse"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.getenv('MCP_API_KEY')}"},
        timeout=30,  # Connection timeout in seconds
    )
    tools = await mcp_server_tools(server_params)

    # Create an agent that can use the translation tool
    model_client = OpenAIChatCompletionClient(
        model=os.getenv("OPENAI_LLM_MODEL", default="gpt-4o"), 
        api_key=os.getenv("OPENAI_API_KEY")
    )
    agent = AssistantAgent(
        name="common_agent",
        model_client=model_client,
        tools=tools,
        system_message="You are a helpful assistant who assist the queries in *Service Now* app. \nImportant: When ever you make tool call, call the tool with {{'params': {{other params}}}}",
    )

    # Let the agent translate some text
    await Console(
        agent.run_stream(task=input("Enter the task: ") , cancellation_token=CancellationToken())
    )


if __name__ == "__main__":
    asyncio.run(main())
