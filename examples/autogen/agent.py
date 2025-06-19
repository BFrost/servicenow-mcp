import asyncio
import os
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import SseServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
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
    # print([(i.name, i.description) for i in tools])

    # Create an agent that can use the tools from MCP service
    model_client = OpenAIChatCompletionClient(
        model=os.getenv("OPENAI_LLM_MODEL", default="gpt-4o"), api_key=os.getenv("OPENAI_API_KEY")
    )

    # Create the assistant agent
    assistant = AssistantAgent(
        name="service_now_assistant",
        model_client=model_client,
        tools=tools,
        system_message="You are a helpful assistant who assists with queries in *Service Now* app. show to the user in a user friendly way"
        "Important: Whenever you make a tool call, call the tool with {'params': {other params}}",
    )

    # Create a user proxy agent
    # By default, it will use the input() function to get user input from console
    user_proxy = UserProxyAgent(
        name="user_proxy",
        input_func=input,  # Use input() to get user input from console
    )

    # Create a termination condition which will end the conversation when the user says "EXIT"
    termination = TextMentionTermination("EXIT")

    # Create the team with both agents
    team = RoundRobinGroupChat([assistant, user_proxy], termination_condition=termination)

    # Initial task from user
    initial_task = input("Enter your Service Now query (type 'EXIT' to end conversation): ")

    # Run the team conversation and stream to console
    stream = team.run_stream(task=initial_task, cancellation_token=CancellationToken())

    # Use asyncio.run(...) when running in a script
    await Console(stream)

    # Close the model client
    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
