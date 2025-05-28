from strands import Agent
from strands_tools import file_read, file_write, editor
from strands.models import BedrockModel
import logging
from os import getenv
import base64
import json
from strands_multi_agent.casual_conversations_agent import general_assistant_agent
from strands_multi_agent.code_generator_agent import code_generator_agent
from strands_multi_agent.ppt_generator_agent import ppt_generator_agent
from strands_multi_agent.weather_agent import weather_agent
from strands_multi_agent.web_search_agent import web_search_agent
from strands_multi_agent.retriever_agent import retriever_agent
import sys
import os
from agent_executor_utils import bedrockModel

logger = logging.getLogger("orchestrator")
wss_url = getenv("WSS_URL", "WEBSOCKET_URL_MISSING")
# Define a focused system prompt for file operations
ORCHESTRATOR_SYSTEM_PROMPT = """
You are a Multi-Agent Orchestrator, designed to coordinate support across multiple agents. Your role is to:

1. Analyze incoming user queries and determine the most appropriate specialized agent to handle them:
   - WebSearch Agent: For searching the web if you dont have the information
   - Retreiver Agent: For RAG if you have the information
   - Code Generator Agent: For code generation. The code generator agent will generate a code and upload it on s3.
                It will provide you the Presigned S3 url where the code is uploaded in <location>...</location> tags. You can use this S3 key to display the code to the user.
   - Weather Agent: For weather information
   - PPT Generator Agent: For presentation generation. The PPT Generator Agent will generate a presentation and upload it on s3.
                It will provide you the Presigned S3 url where the presentation is uploaded in <location>...</location> tags. You can use this S3 key to display the presentation to the user.
                You should pass on the presigned S3 url to the user.
   - General Assistant Agent: For all topics outside the specialized areas

2. Key Responsibilities:
   - Accurately classify user queries by domain area
   - Route requests to the appropriate specialized agent
   - Maintain context and coordinate multi-step problems
   - Ensure cohesive responses when multiple agents are needed

3. Decision Protocol:
   - If query involves weather forecast → WeatherAgent
   - If query involves unknown information → Web Search Agent
   - If query involves data in Knowledge Base → Retreiver Agent
   - If query involves code generation → Code Generator Agent
   - If query is outside these specialized areas → General Assistant Agent
   - if query involves creating a presentation → PPT Generator Agent
   - For complex queries, coordinate multiple agents as needed

Always confirm your understanding before routing to ensure accurate assistance.
When using the PPT Generator Agent, you should pass on the presigned S3 url to the user.
When using the Code Generator Agent, you should pass on the presigned S3 url to the user, so it renders on the UI.
"""


tool_use_ids = []
def orchestrator(user_query, connect_id, websocket_client):

    def callback_handler(**kwargs):
        if "data" in kwargs:
            # Log the streamed data chunks
            # logger.info(kwargs["data"])
            print(kwargs["data"])
            websocket_send(connect_id, kwargs["data"], websocket_client)
        elif "current_tool_use" in kwargs:
            tool = kwargs["current_tool_use"]
            if tool["toolUseId"] not in tool_use_ids:
                # Log the tool use
                logger.info(f"\n[Using tool: {tool.get('name')}]")
                websocket_send(connect_id, f"\n[Using tool: {tool.get('name')}]", websocket_client)
                tool_use_ids.append(tool["toolUseId"])
                
    # Create a new agent with the specified system prompt
    agent = Agent(system_prompt=ORCHESTRATOR_SYSTEM_PROMPT, model=bedrockModel, tools=[general_assistant_agent, 
                                                                        code_generator_agent,
                                                                        ppt_generator_agent, 
                                                                        weather_agent, 
                                                                        web_search_agent, 
                                                                        retriever_agent], callback_handler=callback_handler)
    # Invoke the agent with the user query
    agent_response = agent(user_query)
    # Return the response from the agent
    return str(agent_response)


def websocket_send(connect_id, message, websocket_client):
    global wss_url
    logger.debug(f'WSS URL {wss_url}, connect_id {connect_id}, message {message}')
    response = websocket_client.post_to_connection(
                Data=base64.b64encode(json.dumps(message, indent=4).encode('utf-8')),
                ConnectionId=connect_id
            )
    
# if __name__ == "__main__":
#     print(orchestrator("Create a presentation on NVIDIA for the year 2024 ?", "1234567890"))