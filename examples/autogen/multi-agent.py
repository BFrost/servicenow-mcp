import asyncio
import os
from typing import Sequence, Union

from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import SseServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.messages import AgentEvent, ChatMessage
from autogen_agentchat.teams import SelectorGroupChat
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
    
    # Get all the tools from the MCP server
    all_tools = await mcp_server_tools(server_params)
    
    # Define a dictionary to categorize tools based on their domain
    tools_by_domain = {
        "incident": ["create_incident", "update_incident", "add_comment", "resolve_incident", "list_incidents"],
        "catalog": ["list_catalog_items", "get_catalog_item", "list_catalog_categories", "create_catalog_category", 
                   "update_catalog_category", "move_catalog_items", "get_optimization_recommendations", 
                   "update_catalog_item", "create_catalog_item_variable", "list_catalog_item_variables", 
                   "update_catalog_item_variable"],
        "change": ["create_change_request", "update_change_request", "list_change_requests", 
                  "get_change_request_details", "add_change_task", "submit_change_for_approval", 
                  "approve_change", "reject_change"],
        "workflow": ["list_workflows", "get_workflow_details", "list_workflow_versions", 
                    "get_workflow_activities", "create_workflow", "update_workflow", 
                    "activate_workflow", "deactivate_workflow", "add_workflow_activity", 
                    "update_workflow_activity", "delete_workflow_activity", "reorder_workflow_activities"],
        "script": ["list_script_includes", "get_script_include", "create_script_include", 
                  "update_script_include", "delete_script_include"],
        "changeset": ["list_changesets", "get_changeset_details", "create_changeset", 
                     "update_changeset", "commit_changeset", "publish_changeset", "add_file_to_changeset"],
        "knowledge": ["create_knowledge_base", "list_knowledge_bases", "create_category", 
                     "create_article", "update_article", "publish_article", "list_articles", 
                     "get_article", "list_categories"],
        "user": ["create_user", "update_user", "get_user", "list_users", "create_group", 
                "update_group", "add_group_members", "remove_group_members", "list_groups"],
    }
    
    # Filter the tools for each domain
    domain_tools = {}
    for domain, tool_names in tools_by_domain.items():
        domain_tools[domain] = [tool for tool in all_tools if tool.name in tool_names]
    
    # Create OpenAI model client
    model_client = OpenAIChatCompletionClient(
        model=os.getenv("OPENAI_LLM_MODEL", default="gpt-4o"), 
        api_key=os.getenv("OPENAI_API_KEY"),
        # parallel_tool_calls=False,  # Disable parallel tool calls for better control
    )
    
    # Create the coordinator agent
    coordinator = AssistantAgent(
        name="coordinator",
        model_client=model_client,
        system_message=(
            "You are the ServiceNow coordination agent responsible for handling user requests and "
            "directing them to the appropriate specialist agent:\n"
            "- Incident Manager: For incident-related tasks\n"
            "- Catalog Manager: For service catalog related tasks\n"
            "- Change Manager: For change request related tasks\n"
            "- Workflow Manager: For workflow related tasks\n"
            "- Script Manager: For script include related tasks\n"
            "- Changeset Manager: For changeset related tasks\n"
            "- Knowledge Manager: For knowledge base related tasks\n"
            "- User Manager: For user and group related tasks\n\n"
            "First understand the user's request, then direct it to the most appropriate specialist. "
            "Provide a clear handoff message mentioning which specialist you're directing the task to and why. "
            "After a specialist completes their task, analyze their response and determine if: "
            "1. The task is complete and should be returned to the user\n"
            "2. Another specialist is needed\n"
            "3. Further information is needed from the user\n"
            "Always respond in a helpful, clear manner. When all tasks are complete, confirm with user and Use EXIT word after the user confirmation.\n"
            "Don't tell EXIT before confirming with user"
        ),
    )
    
    # Create specialized agents for each domain
    incident_manager = AssistantAgent(
        name="incident_manager",
        model_client=model_client,
        tools=domain_tools["incident"],
        system_message=(
            "You are a ServiceNow Incident Management specialist. You handle tasks related to "
            "creating, updating, listing, commenting on, and resolving incidents. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    catalog_manager = AssistantAgent(
        name="catalog_manager",
        model_client=model_client,
        tools=domain_tools["catalog"],
        system_message=(
            "You are a ServiceNow Service Catalog Management specialist. You handle tasks related to "
            "service catalog items, categories, and catalog optimization. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    change_manager = AssistantAgent(
        name="change_manager",
        model_client=model_client,
        tools=domain_tools["change"],
        system_message=(
            "You are a ServiceNow Change Management specialist. You handle tasks related to "
            "change requests, including creation, updates, approvals, and tasks within change requests. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    workflow_manager = AssistantAgent(
        name="workflow_manager",
        model_client=model_client,
        tools=domain_tools["workflow"],
        system_message=(
            "You are a ServiceNow Workflow Management specialist. You handle tasks related to "
            "workflows, including creation, updating, activating, and configuring workflow activities. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    script_manager = AssistantAgent(
        name="script_manager",
        model_client=model_client,
        tools=domain_tools["script"],
        system_message=(
            "You are a ServiceNow Script Include Management specialist. You handle tasks related to "
            "listing, creating, updating, and deleting script includes in ServiceNow. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    changeset_manager = AssistantAgent(
        name="changeset_manager",
        model_client=model_client,
        tools=domain_tools["changeset"],
        system_message=(
            "You are a ServiceNow Changeset Management specialist. You handle tasks related to "
            "changesets, including creation, updating, committing, publishing, and adding files. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    knowledge_manager = AssistantAgent(
        name="knowledge_manager",
        model_client=model_client,
        tools=domain_tools["knowledge"],
        system_message=(
            "You are a ServiceNow Knowledge Base Management specialist. You handle tasks related to "
            "knowledge bases, articles, and categories. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    user_manager = AssistantAgent(
        name="user_manager",
        model_client=model_client,
        tools=domain_tools["user"],
        system_message=(
            "You are a ServiceNow User Management specialist. You handle tasks related to "
            "users and groups, including creation, updates, and listings. "
            "Important: Whenever you make a tool call, call the tool with {'params': {other params}}. "
            "Always format results in a clean, readable manner. When your task is complete, pass control back to the coordinator.\n"
            "If you need any information from User for"
        ),
    )
    
    # Create a user proxy agent
    user_proxy = UserProxyAgent(
        name="user_proxy",
        input_func=input,  # Use input() to get user input from console
    )
    
    # Define custom selector function
    def selector_func(messages: Sequence[Union[AgentEvent, ChatMessage]]) -> str:
        """Custom selector function that returns to the coordinator after a specialist speaks."""
        
        if not messages:
            return None
            
        last_message = messages[-1]
        last_speaker = getattr(last_message, "source", None)
        
        # If the last speaker was the user, go to the coordinator
        if last_speaker == "user_proxy":
            return "coordinator"
            
        # If the last speaker was the coordinator, let the model decide the next speaker
        if last_speaker == "coordinator":
            return None
            
        # If the last speaker was any specialist agent, always return to the coordinator
        specialist_agents = ["incident_manager", "catalog_manager", "change_manager", 
                            "workflow_manager", "script_manager", "changeset_manager", 
                            "knowledge_manager", "user_manager"]
        if last_speaker in specialist_agents:
            return "coordinator"
            
        return None
    
    # Create selector prompt
    selector_prompt = """Select the next agent to respond based on the conversation context.

Available agents:
{roles}

Agent descriptions:
{participants}

Conversation history:
{history}

Based on the conversation, select the most appropriate agent to respond next. If a specialist agent just responded, direct the conversation back to the coordinator for next steps. If the user just shared input, direct to the coordinator to analyze.

Select exactly one agent from {participants} to speak next.
"""
    
    # Define all agents
    all_agents = [
        coordinator,
        incident_manager,
        catalog_manager,
        change_manager,
        workflow_manager,
        script_manager,
        changeset_manager,
        knowledge_manager,
        user_manager,
        user_proxy
    ]
    
    # Create a termination condition which will end the conversation when "EXIT" is mentioned
    termination = TextMentionTermination("EXIT")
    
    # Create the team with SelectorGroupChat
    team = SelectorGroupChat(
        all_agents,
        model_client=model_client,
        termination_condition=termination,
        selector_prompt=selector_prompt,
        selector_func=selector_func,
        allow_repeated_speaker=True,  # This allows the same agent to speak again if needed
    )
    
    # Initial task from user
    initial_task = input("Enter your ServiceNow query (type 'EXIT' to end conversation): ")
    
    # Run the team conversation and stream to console
    try:
        stream = team.run_stream(task=initial_task, cancellation_token=CancellationToken())
        await Console(stream)
    finally:
        # Close the model client
        await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())