import pytest
import aws_cdk as cdk


@pytest.fixture
def app():
    return cdk.App(context={
        "environment_name": "test",
        "is_aoss": "yes",
        "embed_model_id": "amazon.titan-embed-text-v2:0",
        "test": {
            "collection_name": "srd-vectors-test",
            "collection_group_name": "srd-group-test",
            "index_name": "srd-embeddings-test",
            "s3_data_bucket": "srd-store-test",
            "rag-llm-user-pool": "srd-auth-test",
            "rag-llm-cognito": "srd-cognito-test",
            "knowledge_base_name": "srd-kb-test",
            "agentcore_multi_agent": "srd-multi-agent-test",
            "agentcore_rag_query": "srd-rag-query-test",
            "default_llm_model": "global.anthropic.claude-sonnet-4-6-v1:0",
            "embed_model_id": "amazon.titan-embed-text-v2:0",
            "ocu_mode": "demo",
        }
    })


@pytest.fixture
def stack(app):
    return cdk.Stack(app, "TestStack", env=cdk.Environment(account="123456789012", region="us-east-1"))
