"""Managed web search through the AgentCore Gateway.

This replaces strands_tools.http_request. That tool let the model choose any URL
it liked, which meant a prompt-injected document could aim the runtime's own
credentials at the instance metadata endpoint or at an internal address — the
model was the only thing standing between a crafted document and the role's S3
access.

The Gateway's web-search connector is a managed primitive: it takes a search
string and returns results, so there is no URL for the model to control and no
request that leaves with our credentials attached. The connector is reached over
MCP with SigV4, so access is an IAM decision rather than a prompting one.

GATEWAY_URL is empty when the deployment's region or CLI did not support the
connector; web search then reports itself unavailable rather than silently
falling back to an unrestricted fetch.
"""

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "")
REGION = os.getenv("REGION", "us-east-1")

# The connector caps the query at 200 characters and maxResults at 25.
MAX_RESULTS = 5


class WebSearchUnavailable(RuntimeError):
    """No Gateway is configured for this deployment."""


@contextmanager
def web_search_tools():
    """Yield the Gateway's tools, usable only inside the context manager."""
    if not GATEWAY_URL:
        raise WebSearchUnavailable("No AgentCore Gateway is configured")

    # Imported here so a deployment without the Gateway does not need the
    # package present to start up.
    from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
    from strands.tools.mcp.mcp_client import MCPClient

    client = MCPClient(lambda: aws_iam_streamablehttp_client(
        endpoint=GATEWAY_URL,
        aws_service="bedrock-agentcore",
        aws_region=REGION,
    ))

    with client:
        yield client.list_tools_sync()


def run_with_web_search(query: str, system_prompt: str, model) -> str:
    """Answer `query` with an agent whose only tool is managed web search."""
    from strands import Agent

    try:
        with web_search_tools() as tools:
            agent = Agent(system_prompt=system_prompt, model=model, tools=tools)
            return str(agent(query))
    except WebSearchUnavailable:
        return "Web search is not available in this deployment."
    except Exception:
        logger.exception("Web search failed")
        return "Web search could not be completed."
