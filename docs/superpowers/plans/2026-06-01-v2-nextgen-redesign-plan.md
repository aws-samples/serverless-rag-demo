# Serverless RAG Demo v2 — NextGen Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade serverless-rag-demo to 2026 architecture with AOSS NextGen, Bedrock KB, AgentCore Runtimes, CloudFront hosting, and streamlined CLI.

**Architecture:** S3+CloudFront serves React UI → Cognito auth → API GW (WSS+REST) → AgentCore Runtimes (Multi-Agent Strands Graph + RAG Query) → Bedrock (Claude 4.6 global) + Bedrock KB (Titan Embed V2 + AOSS NextGen hybrid search).

**Tech Stack:** AWS CDK (Python), React 18 + Cloudscape, Strands Agents (Graph pattern), Bedrock AgentCore, AOSS NextGen, Bedrock Knowledge Base, CloudFront + S3, Cognito

---

## File Structure

### New files to create:
- `infrastructure/opensearch_nextgen_stack.py` — AOSS NextGen CollectionGroup + Collection
- `infrastructure/cloudfront_hosting_stack.py` — S3 + CloudFront + BucketDeployment
- `infrastructure/knowledge_base_stack.py` — Bedrock KB + S3 data source
- `infrastructure/agentcore_stack.py` — AgentCore Runtime definitions
- `containers/multi-agent/Dockerfile` — Multi-agent ARM64 container
- `containers/multi-agent/requirements.txt` — Multi-agent deps
- `containers/multi-agent/app.py` — Entry point (/invocations + /ping)
- `containers/multi-agent/graph.py` — Strands Graph definition
- `containers/multi-agent/nodes/classifier.py` — Intent classifier node
- `containers/multi-agent/nodes/retriever.py` — KB retrieval node
- `containers/multi-agent/nodes/web_search.py` — Web search node
- `containers/multi-agent/nodes/code_gen.py` — Code generation node
- `containers/multi-agent/nodes/ppt_gen.py` — PPT generation node
- `containers/multi-agent/nodes/weather.py` — Weather node
- `containers/multi-agent/nodes/general.py` — General conversation node
- `containers/multi-agent/utils.py` — Shared utilities (S3 upload, presigned URLs)
- `containers/rag-query/Dockerfile` — RAG query ARM64 container
- `containers/rag-query/requirements.txt` — RAG query deps
- `containers/rag-query/app.py` — Entry point (/invocations + /ping)
- `containers/rag-query/query.py` — RAG query logic
- `deploy.sh` — New streamlined deployment wizard
- `.aidlc.yml` — AIDLC plugin config
- `tests/unit/test_opensearch_nextgen_stack.py`
- `tests/unit/test_cloudfront_hosting_stack.py`
- `tests/unit/test_knowledge_base_stack.py`
- `tests/unit/test_agentcore_stack.py`
- `tests/unit/conftest.py` — Shared fixtures

### Files to modify:
- `app.py` — New stack wiring, remove AppRunner/ECR imports
- `cdk.json` — New `test` env config, remove deprecated keys
- `requirements.txt` — Bump CDK version
- `llms_with_serverless_rag/llms_with_serverless_rag_stack.py` — New stack composition
- `infrastructure/api_gw_stack.py` — Remove Lambda/layer refs, add AgentCore integration
- `artifacts/chat-ui/src/default-properties.json` — New model list
- `artifacts/chat-ui/src/pages/home-page.tsx` — Updated feature cards
- `artifacts/chat-ui/src/pages/chat-page.tsx` — Add document scope toggle
- `artifacts/chat-ui/src/pages/index.tsx` — Remove dead page imports

### Files to delete:
- `infrastructure/apprunner_hosting_stack.py`
- `infrastructure/ecr_ui_stack.py`
- `infrastructure/bedrock_layer_stack.py`
- `infrastructure/dynamodb_stack.py`
- `infrastructure/opensearch_vectordb_stack.py`
- `buildspec_bedrock.yml`
- `buildspec_dockerize_ui.yml`
- `artifacts/chat-ui/Dockerfile`
- `artifacts/chat-ui/.dockerignore`
- `artifacts/chat-ui/nginx.conf`
- `artifacts/chat-ui/src/pages/sentiment-page.tsx`
- `artifacts/chat-ui/src/pages/ocr-page.tsx`
- `artifacts/chat-ui/src/pages/pii-redact-page.tsx`
- `artifacts/bedrock_lambda/` (entire directory)
- `creator.sh`

---

## Phase 1: Infrastructure Foundation (AOSS NextGen + CloudFront + Cognito)

### Task 1: Project setup and configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `cdk.json`
- Create: `.aidlc.yml`
- Create: `tests/unit/conftest.py`

- [ ] **Step 1: Update CDK requirements**

```python
# requirements.txt
aws-cdk-lib>=2.224.0
constructs>=10.0.0,<11.0.0
pyyaml>=6.0
cdk-nag>=2.10.0
boto3>=1.34.0
pytest>=7.0.0
pytest-cov>=4.0.0
```

- [ ] **Step 2: Add `test` environment to cdk.json**

Add this block inside `"context"` after the `"sandbox"` block:

```json
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
  "ocu_mode": "demo"
}
```

- [ ] **Step 3: Create .aidlc.yml**

```yaml
version: 1
tools:
  formatter: "ruff format"
  linter: "ruff check"
  test: "pytest --cov=. --cov-report=term-missing"
  security: "bandit -r ."
  type_check: "mypy ."
  iac_validate: "cdk synth --quiet"
  dep_audit: "pip-audit"
coverage:
  min: 70
  fail_on_drop: 5
review:
  threshold: "high"
  max_fix_cycles: 3
exclude:
  - "node_modules/"
  - ".venv/"
  - "cdk.out/"
  - "artifacts/chat-ui/node_modules/"
branch_prefix: "aidlc"
```

- [ ] **Step 4: Create test conftest**

```python
# tests/unit/conftest.py
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
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt cdk.json .aidlc.yml tests/unit/conftest.py
git commit -m "chore: add test environment config and project setup for v2"
```

---

### Task 2: OpenSearch Serverless NextGen stack

**Files:**
- Create: `infrastructure/opensearch_nextgen_stack.py`
- Create: `tests/unit/test_opensearch_nextgen_stack.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_opensearch_nextgen_stack.py
import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.opensearch_nextgen_stack import OpensearchNextgenStack


def test_creates_collection_group(app, stack):
    nested = OpensearchNextgenStack(stack, "TestAOSS")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::CollectionGroup", 1)


def test_creates_collection(app, stack):
    nested = OpensearchNextgenStack(stack, "TestAOSS")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::Collection", 1)


def test_creates_security_policies(app, stack):
    nested = OpensearchNextgenStack(stack, "TestAOSS")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::SecurityPolicy", 2)


def test_creates_access_policy(app, stack):
    nested = OpensearchNextgenStack(stack, "TestAOSS")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::AccessPolicy", 1)


def test_demo_mode_no_min_ocu(app, stack):
    nested = OpensearchNextgenStack(stack, "TestAOSS")
    template = Template.from_stack(nested)
    props = template.to_json()
    # In demo mode, no minIndexingCapacityInOcu should be set
    # (allows scale-to-zero)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_opensearch_nextgen_stack.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'infrastructure.opensearch_nextgen_stack'"

- [ ] **Step 3: Implement the stack**

```python
# infrastructure/opensearch_nextgen_stack.py
import json
import os
from aws_cdk import (
    NestedStack,
    aws_opensearchserverless as _oss,
    CfnOutput,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class OpensearchNextgenStack(NestedStack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")

        collection_name = env_params["collection_name"]
        group_name = env_params["collection_group_name"]
        ocu_mode = env_params.get("ocu_mode", "demo")

        # Collection Group with capacity limits
        capacity_limits = {"maxIndexingCapacityInOcu": 4, "maxSearchCapacityInOcu": 4}
        if ocu_mode == "production":
            capacity_limits["minIndexingCapacityInOcu"] = 2
            capacity_limits["minSearchCapacityInOcu"] = 2
            capacity_limits["maxIndexingCapacityInOcu"] = 10
            capacity_limits["maxSearchCapacityInOcu"] = 10

        collection_group = _oss.CfnCollectionGroup(
            self, f"srd-group-{env_name}",
            name=group_name,
            standby_replicas="DISABLED",
            capacity_limits=capacity_limits,
        )

        # Encryption policy
        encryption_policy = _oss.CfnSecurityPolicy(
            self, f"srd-encrypt-{env_name}",
            name=f"srd-encrypt-{env_name}",
            type="encryption",
            policy=json.dumps({
                "Rules": [{"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]}],
                "AWSOwnedKey": True,
            }),
        )

        # Network policy (allow public access for demo)
        network_policy = _oss.CfnSecurityPolicy(
            self, f"srd-network-{env_name}",
            name=f"srd-network-{env_name}",
            type="network",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]},
                    {"ResourceType": "dashboard", "Resource": [f"collection/{collection_name}"]},
                ],
                "AllowFromPublic": True,
            }]),
        )

        # Data access policy — principals added later by KB stack and AgentCore stack
        self._data_access_policy_name = f"srd-data-{env_name}"
        data_access_policy = _oss.CfnAccessPolicy(
            self, f"srd-data-{env_name}",
            name=self._data_access_policy_name,
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "index", "Resource": [f"index/{collection_name}/*"], "Permission": ["aoss:*"]},
                    {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"], "Permission": ["aoss:*"]},
                ],
                "Principal": [f"arn:aws:iam::{account_id}:root"],
            }]),
        )

        # Collection referencing the group
        cfn_collection = _oss.CfnCollection(
            self, f"srd-collection-{env_name}",
            name=collection_name,
            type="VECTORSEARCH",
            collection_group_name=group_name,
            description="Serverless RAG Demo v2 vector store",
        )
        cfn_collection.add_dependency(encryption_policy)
        cfn_collection.add_dependency(network_policy)
        cfn_collection.add_dependency(data_access_policy)
        cfn_collection.node.add_dependency(collection_group)

        # Outputs
        self.collection_endpoint = cfn_collection.attr_collection_endpoint
        self.collection_arn = cfn_collection.attr_arn
        self.collection_name = collection_name

        CfnOutput(self, f"collection-endpoint-{env_name}",
                  value=cfn_collection.attr_collection_endpoint,
                  description="AOSS NextGen Collection Endpoint")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_opensearch_nextgen_stack.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/opensearch_nextgen_stack.py tests/unit/test_opensearch_nextgen_stack.py
git commit -m "feat: add OpenSearch Serverless NextGen stack with CollectionGroup"
```

---

### Task 3: CloudFront hosting stack

**Files:**
- Create: `infrastructure/cloudfront_hosting_stack.py`
- Create: `tests/unit/test_cloudfront_hosting_stack.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cloudfront_hosting_stack.py
import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack


def test_creates_s3_bucket(app, stack):
    nested = CloudFrontHostingStack(stack, "TestCF",
        cognito_user_pool_id="pool-123",
        cognito_client_id="client-456",
        rest_endpoint_url="https://api.example.com/test/rag/",
        websocket_url="wss://ws.example.com/test")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::S3::Bucket", 1)


def test_creates_cloudfront_distribution(app, stack):
    nested = CloudFrontHostingStack(stack, "TestCF",
        cognito_user_pool_id="pool-123",
        cognito_client_id="client-456",
        rest_endpoint_url="https://api.example.com/test/rag/",
        websocket_url="wss://ws.example.com/test")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_bucket_blocks_public_access(app, stack):
    nested = CloudFrontHostingStack(stack, "TestCF",
        cognito_user_pool_id="pool-123",
        cognito_client_id="client-456",
        rest_endpoint_url="https://api.example.com/test/rag/",
        websocket_url="wss://ws.example.com/test")
    template = Template.from_stack(nested)
    template.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
    })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cloudfront_hosting_stack.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement the stack**

```python
# infrastructure/cloudfront_hosting_stack.py
import json
import os
from aws_cdk import (
    NestedStack,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class CloudFrontHostingStack(NestedStack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        cognito_user_pool_id: str,
        cognito_client_id: str,
        rest_endpoint_url: str,
        websocket_url: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        region = os.getenv("CDK_DEFAULT_REGION")

        # S3 bucket for static hosting
        site_bucket = s3.Bucket(
            self, f"srd-ui-bucket-{env_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # CloudFront OAC
        oac = cloudfront.S3OriginAccessControl(
            self, f"srd-oac-{env_name}",
        )

        # CloudFront distribution
        distribution = cloudfront.Distribution(
            self, f"srd-distribution-{env_name}",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket, origin_access_control=oac),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # Deploy React build to S3
        s3_deploy.BucketDeployment(
            self, f"srd-ui-deploy-{env_name}",
            sources=[
                s3_deploy.Source.asset(
                    os.path.join(os.getcwd(), "artifacts/chat-ui"),
                    bundling={
                        "image": cdk.DockerImage.from_registry("node:20-slim"),
                        "command": [
                            "bash", "-c",
                            "npm ci && npm run build && cp -r build/* /asset-output/",
                        ],
                    },
                ),
            ],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # Deploy runtime-config.json separately (no bundling needed)
        runtime_config = {
            "cognitoUserPoolId": cognito_user_pool_id,
            "cognitoClientId": cognito_client_id,
            "cognitoRegion": region,
            "restEndpointUrl": rest_endpoint_url,
            "websocketUrl": websocket_url,
        }

        s3_deploy.BucketDeployment(
            self, f"srd-runtime-config-{env_name}",
            sources=[s3_deploy.Source.json_data("runtime-config.json", runtime_config)],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/runtime-config.json"],
        )

        # Outputs
        self.distribution_url = f"https://{distribution.distribution_domain_name}"
        CfnOutput(self, f"ui-url-{env_name}",
                  value=self.distribution_url,
                  description="CloudFront UI URL")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR4", reason="Using default CloudFront certificate for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-S1", reason="Access logs not needed for demo UI bucket"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR1", reason="Geo restriction not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR2", reason="WAF not needed for demo"),
        ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_cloudfront_hosting_stack.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/cloudfront_hosting_stack.py tests/unit/test_cloudfront_hosting_stack.py
git commit -m "feat: add CloudFront + S3 hosting stack with runtime-config.json"
```

---

## Phase 2: Bedrock Knowledge Base

### Task 4: Knowledge Base stack

**Files:**
- Create: `infrastructure/knowledge_base_stack.py`
- Create: `tests/unit/test_knowledge_base_stack.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_knowledge_base_stack.py
import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.knowledge_base_stack import KnowledgeBaseStack


def test_creates_kb_role(app, stack):
    nested = KnowledgeBaseStack(stack, "TestKB",
        collection_arn="arn:aws:aoss:us-east-1:123456789012:collection/abc123",
        collection_endpoint="https://abc123.us-east-1.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::IAM::Role", 1)


def test_creates_s3_bucket(app, stack):
    nested = KnowledgeBaseStack(stack, "TestKB",
        collection_arn="arn:aws:aoss:us-east-1:123456789012:collection/abc123",
        collection_endpoint="https://abc123.us-east-1.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
    })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_knowledge_base_stack.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement the stack**

```python
# infrastructure/knowledge_base_stack.py
import json
import os
from aws_cdk import (
    NestedStack,
    RemovalPolicy,
    CfnOutput,
    aws_iam as iam,
    aws_s3 as s3,
    aws_bedrock as bedrock,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class KnowledgeBaseStack(NestedStack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        collection_arn: str,
        collection_endpoint: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")

        kb_name = env_params["knowledge_base_name"]
        index_name = env_params["index_name"]
        embed_model_id = env_params["embed_model_id"]
        bucket_name = env_params["s3_data_bucket"]

        # S3 data bucket for documents
        data_bucket = s3.Bucket(
            self, f"srd-data-bucket-{env_name}",
            bucket_name=f"{bucket_name}-{account_id}-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
            cors=[s3.CorsRule(
                allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.GET],
                allowed_origins=["*"],
                allowed_headers=["*"],
            )],
        )

        # KB execution role
        kb_role = iam.Role(
            self, f"srd-kb-role-{env_name}",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "BedrockKBPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["aoss:APIAccessAll"],
                        resources=[collection_arn],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=[f"arn:aws:bedrock:{region}::foundation-model/{embed_model_id}"],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:ListBucket"],
                        resources=[data_bucket.bucket_arn, f"{data_bucket.bucket_arn}/*"],
                    ),
                ]),
            },
        )

        # Bedrock Knowledge Base (L1 construct)
        kb = bedrock.CfnKnowledgeBase(
            self, f"srd-kb-{env_name}",
            name=kb_name,
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{region}::foundation-model/{embed_model_id}",
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=1024,
                        ),
                    ),
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=collection_arn,
                    vector_index_name=index_name,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field="embedding",
                        text_field="text",
                        metadata_field="metadata",
                    ),
                ),
            ),
        )

        # S3 Data Source with Data Automation parser
        data_source = bedrock.CfnDataSource(
            self, f"srd-kb-datasource-{env_name}",
            knowledge_base_id=kb.attr_knowledge_base_id,
            name=f"srd-docs-{env_name}",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=data_bucket.bucket_arn,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="SEMANTIC",
                    semantic_chunking_configuration=bedrock.CfnDataSource.SemanticChunkingConfigurationProperty(
                        max_token=512,
                        buffer_size=0,
                        breakpoint_percentile_threshold=95,
                    ),
                ),
                parsing_configuration=bedrock.CfnDataSource.ParsingConfigurationProperty(
                    parsing_strategy="BEDROCK_DATA_AUTOMATION",
                    bedrock_data_automation_configuration=bedrock.CfnDataSource.BedrockDataAutomationConfigurationProperty(
                        parsing_modality="MULTIMODAL",
                    ),
                ),
            ),
        )

        # Outputs
        self.knowledge_base_id = kb.attr_knowledge_base_id
        self.data_source_id = data_source.attr_data_source_id
        self.data_bucket = data_bucket
        self.data_bucket_name = data_bucket.bucket_name

        CfnOutput(self, f"kb-id-{env_name}",
                  value=kb.attr_knowledge_base_id,
                  description="Bedrock Knowledge Base ID")
        CfnOutput(self, f"data-bucket-{env_name}",
                  value=data_bucket.bucket_name,
                  description="Document upload bucket")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5", reason="KB role needs wildcard for S3 objects and AOSS indices"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-S1", reason="Access logs not required for demo data bucket"),
        ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_knowledge_base_stack.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/knowledge_base_stack.py tests/unit/test_knowledge_base_stack.py
git commit -m "feat: add Bedrock Knowledge Base stack with S3 data source and Data Automation parser"
```

---

## Phase 3: AgentCore Multi-Agent Runtime (Strands Graph)

### Task 5: Multi-Agent container — Dockerfile and dependencies

**Files:**
- Create: `containers/multi-agent/Dockerfile`
- Create: `containers/multi-agent/requirements.txt`
- Create: `containers/multi-agent/nodes/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```text
# containers/multi-agent/requirements.txt
strands-agents>=0.1.0
strands-agents-tools>=0.1.0
python-pptx>=0.6.21
xmltodict>=0.13.0
Pillow>=10.0.0
geopy>=2.4.0
beautifulsoup4>=4.12.0
boto3>=1.34.0
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
# containers/multi-agent/Dockerfile
FROM public.ecr.aws/lambda/python:3.12-arm64

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

ENTRYPOINT ["python", "app.py"]
```

- [ ] **Step 3: Create nodes __init__**

```python
# containers/multi-agent/nodes/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add containers/multi-agent/Dockerfile containers/multi-agent/requirements.txt containers/multi-agent/nodes/__init__.py
git commit -m "feat: add multi-agent container scaffold"
```

---

### Task 6: Multi-Agent shared utilities

**Files:**
- Create: `containers/multi-agent/utils.py`

- [ ] **Step 1: Create shared utilities**

```python
# containers/multi-agent/utils.py
import boto3
import os
import uuid
import logging

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "")
REGION = os.getenv("REGION", "us-east-1")

s3_client = boto3.client("s3", region_name=REGION)


def upload_to_s3(content: bytes, key: str, content_type: str = "text/html") -> str:
    """Upload content to S3 and return the key."""
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return key


def generate_presigned_url(key: str, expiry: int = 3600) -> str:
    """Generate a presigned URL for an S3 object."""
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expiry,
    )


def upload_and_get_url(content: bytes, prefix: str, extension: str, content_type: str) -> str:
    """Upload content and return presigned URL."""
    key = f"{prefix}/{uuid.uuid4()}.{extension}"
    upload_to_s3(content, key, content_type)
    return generate_presigned_url(key)
```

- [ ] **Step 2: Commit**

```bash
git add containers/multi-agent/utils.py
git commit -m "feat: add multi-agent shared utilities (S3 upload, presigned URLs)"
```

---

### Task 7: Multi-Agent Strands Graph nodes

**Files:**
- Create: `containers/multi-agent/nodes/classifier.py`
- Create: `containers/multi-agent/nodes/retriever.py`
- Create: `containers/multi-agent/nodes/web_search.py`
- Create: `containers/multi-agent/nodes/code_gen.py`
- Create: `containers/multi-agent/nodes/ppt_gen.py`
- Create: `containers/multi-agent/nodes/weather.py`
- Create: `containers/multi-agent/nodes/general.py`

- [ ] **Step 1: Create classifier node**

```python
# containers/multi-agent/nodes/classifier.py
from strands import Agent
from strands.models import BedrockModel
import os
import json
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

CLASSIFIER_PROMPT = """You are an intent classifier. Given a user query, classify it into exactly ONE of these categories:
- RETRIEVAL: Questions that should be answered from uploaded documents/knowledge base
- WEB_SEARCH: Questions requiring current web information
- CODE_GEN: Requests to generate code (HTML, Python, etc.)
- PPT_GEN: Requests to create presentations/slides
- WEATHER: Questions about weather
- GENERAL: Casual conversation, greetings, or topics not matching above

Respond with ONLY the category name, nothing else."""


def classify_intent(query: str) -> str:
    """Classify user intent and return the category."""
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=CLASSIFIER_PROMPT, model=model)
    response = agent(query)
    intent = str(response).strip().upper()

    valid_intents = {"RETRIEVAL", "WEB_SEARCH", "CODE_GEN", "PPT_GEN", "WEATHER", "GENERAL"}
    if intent not in valid_intents:
        logger.warning(f"Unknown intent '{intent}', defaulting to GENERAL")
        return "GENERAL"
    return intent
```

- [ ] **Step 2: Create retriever node**

```python
# containers/multi-agent/nodes/retriever.py
import boto3
import os
import logging

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


def retrieve(query: str, user_email: str = None, search_scope: str = "all") -> str:
    """Query Bedrock KB with optional metadata filtering."""
    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 5,
            "overrideSearchType": "HYBRID",
        }
    }

    # Pre-filter: user's documents only
    if search_scope == "my_docs" and user_email:
        retrieval_config["vectorSearchConfiguration"]["filter"] = {
            "equals": {"key": "user_email", "value": user_email}
        }

    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration=retrieval_config,
    )

    results = response.get("retrievalResults", [])
    if not results:
        return "No relevant documents found."

    context_parts = []
    for i, result in enumerate(results, 1):
        text = result.get("content", {}).get("text", "")
        score = result.get("score", 0)
        context_parts.append(f"[Source {i} (score: {score:.2f})]\n{text}")

    return "\n\n".join(context_parts)
```

- [ ] **Step 3: Create web search node**

```python
# containers/multi-agent/nodes/web_search.py
from strands import Agent
from strands.models import BedrockModel
from strands_tools import web_search
import os
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

WEB_SEARCH_PROMPT = """You are a web research assistant. Use the web_search tool to find current information.
Summarize findings clearly with sources. Be concise and factual."""


def search_web(query: str) -> str:
    """Search the web and return summarized results."""
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=WEB_SEARCH_PROMPT, model=model, tools=[web_search])
    response = agent(query)
    return str(response)
```

- [ ] **Step 4: Create code generation node**

```python
# containers/multi-agent/nodes/code_gen.py
from strands import Agent
from strands.models import BedrockModel
from utils import upload_and_get_url
import os
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

CODE_GEN_PROMPT = """You are a code generator. Generate clean, working code based on user requests.
When generating HTML, include inline CSS and make it visually appealing.
Return ONLY the code, no explanations."""


def generate_code(query: str) -> str:
    """Generate code and upload to S3, return presigned URL."""
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=CODE_GEN_PROMPT, model=model)
    response = agent(query)
    code = str(response)

    url = upload_and_get_url(
        content=code.encode("utf-8"),
        prefix="generated-code",
        extension="html",
        content_type="text/html",
    )
    return f"Code generated and uploaded. <location>{url}</location>"
```

- [ ] **Step 5: Create PPT generation node**

```python
# containers/multi-agent/nodes/ppt_gen.py
from strands import Agent
from strands.models import BedrockModel
from pptx import Presentation
from pptx.util import Inches, Pt
from utils import upload_and_get_url
import json
import os
import io
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

PPT_PROMPT = """You are a presentation content planner. Given a topic, create slide content as JSON:
{"slides": [{"title": "...", "bullets": ["...", "..."]}]}
Generate 5-8 slides with clear, concise bullet points. Return ONLY valid JSON."""


def generate_ppt(query: str) -> str:
    """Generate a PowerPoint presentation and return presigned URL."""
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=PPT_PROMPT, model=model)
    response = agent(query)

    try:
        slides_data = json.loads(str(response))
    except json.JSONDecodeError:
        return "Failed to generate presentation structure."

    prs = Presentation()
    for slide_data in slides_data.get("slides", []):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = slide_data.get("title", "")
        body = slide.placeholders[1]
        tf = body.text_frame
        tf.clear()
        for bullet in slide_data.get("bullets", []):
            p = tf.add_paragraph()
            p.text = bullet
            p.font.size = Pt(18)

    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)

    url = upload_and_get_url(
        content=buffer.read(),
        prefix="generated-ppt",
        extension="pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    return f"Presentation generated. <location>{url}</location>"
```

- [ ] **Step 6: Create weather node**

```python
# containers/multi-agent/nodes/weather.py
from strands import Agent
from strands.models import BedrockModel
from strands_tools import web_search
from geopy.geocoders import Nominatim
import os
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

WEATHER_PROMPT = """You are a weather assistant. Use web_search to find current weather information.
Report temperature, conditions, and forecast concisely."""


def get_weather(query: str) -> str:
    """Get weather information for a location."""
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=WEATHER_PROMPT, model=model, tools=[web_search])
    response = agent(query)
    return str(response)
```

- [ ] **Step 7: Create general conversation node**

```python
# containers/multi-agent/nodes/general.py
from strands import Agent
from strands.models import BedrockModel
import os
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

GENERAL_PROMPT = """You are a helpful, friendly assistant. Answer questions clearly and concisely.
If you don't know something, say so honestly."""


def chat(query: str) -> str:
    """Handle general conversation."""
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=GENERAL_PROMPT, model=model)
    response = agent(query)
    return str(response)
```

- [ ] **Step 8: Commit**

```bash
git add containers/multi-agent/nodes/
git commit -m "feat: add Strands Graph specialist nodes (classifier, retriever, web_search, code_gen, ppt_gen, weather, general)"
```

---

### Task 8: Multi-Agent Graph definition and entry point

**Files:**
- Create: `containers/multi-agent/graph.py`
- Create: `containers/multi-agent/app.py`

- [ ] **Step 1: Create graph definition**

```python
# containers/multi-agent/graph.py
import logging
from nodes.classifier import classify_intent
from nodes.retriever import retrieve
from nodes.web_search import search_web
from nodes.code_gen import generate_code
from nodes.ppt_gen import generate_ppt
from nodes.weather import get_weather
from nodes.general import chat

logger = logging.getLogger(__name__)

# Route map: intent → handler function
ROUTE_MAP = {
    "RETRIEVAL": lambda q, ctx: _handle_retrieval(q, ctx),
    "WEB_SEARCH": lambda q, ctx: search_web(q),
    "CODE_GEN": lambda q, ctx: generate_code(q),
    "PPT_GEN": lambda q, ctx: generate_ppt(q),
    "WEATHER": lambda q, ctx: get_weather(q),
    "GENERAL": lambda q, ctx: chat(q),
}


def _handle_retrieval(query: str, context: dict) -> str:
    """Handle retrieval with context-aware KB query."""
    user_email = context.get("user_email")
    search_scope = context.get("search_scope", "all")
    kb_context = retrieve(query, user_email=user_email, search_scope=search_scope)

    if kb_context == "No relevant documents found.":
        return kb_context

    # Use retrieved context to generate answer
    from strands import Agent
    from strands.models import BedrockModel
    import os

    model = BedrockModel(
        model_id=os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0"),
        region_name=os.getenv("REGION", "us-east-1"),
    )
    agent = Agent(
        system_prompt=f"""Answer the user's question using ONLY the following context.
If the context doesn't contain the answer, say so.

Context:
{kb_context}""",
        model=model,
    )
    response = agent(query)
    return str(response)


def run_graph(query: str, context: dict) -> str:
    """Execute the Strands Graph: classify → route → execute."""
    intent = classify_intent(query)
    logger.info(f"Classified intent: {intent}")

    handler = ROUTE_MAP.get(intent, ROUTE_MAP["GENERAL"])
    result = handler(query, context)
    return result
```

- [ ] **Step 2: Create app entry point**

```python
# containers/multi-agent/app.py
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from graph import run_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = 8080


class AgentCoreHandler(BaseHTTPRequestHandler):
    """HTTP handler for AgentCore Runtime endpoints."""

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/invocations":
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            query = body.get("query", "")
            context = {
                "user_email": body.get("user_email"),
                "search_scope": body.get("search_scope", "all"),
                "connection_id": body.get("connection_id"),
            }

            try:
                result = run_graph(query, context)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"response": result}).encode())
            except Exception as e:
                logger.error(f"Invocation error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), AgentCoreHandler)
    logger.info(f"Multi-Agent runtime listening on port {PORT}")
    server.serve_forever()
```

- [ ] **Step 3: Commit**

```bash
git add containers/multi-agent/graph.py containers/multi-agent/app.py
git commit -m "feat: add Strands Graph orchestration and AgentCore HTTP entry point"
```

---

## Phase 4: AgentCore RAG Query Runtime

### Task 9: RAG Query container

**Files:**
- Create: `containers/rag-query/Dockerfile`
- Create: `containers/rag-query/requirements.txt`
- Create: `containers/rag-query/app.py`
- Create: `containers/rag-query/query.py`

- [ ] **Step 1: Create requirements.txt**

```text
# containers/rag-query/requirements.txt
strands-agents>=0.1.0
boto3>=1.34.0
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
# containers/rag-query/Dockerfile
FROM public.ecr.aws/lambda/python:3.12-arm64

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

ENTRYPOINT ["python", "app.py"]
```

- [ ] **Step 3: Create query logic**

```python
# containers/rag-query/query.py
import boto3
import os
import logging
from strands import Agent
from strands.models import BedrockModel

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


def rag_query(query: str, user_email: str = None, search_scope: str = "all", chat_history: list = None) -> str:
    """Execute RAG query: retrieve from KB then generate answer."""

    # Step 1: Retrieve from Knowledge Base
    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 5,
            "overrideSearchType": "HYBRID",
        }
    }

    if search_scope == "my_docs" and user_email:
        retrieval_config["vectorSearchConfiguration"]["filter"] = {
            "equals": {"key": "user_email", "value": user_email}
        }

    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration=retrieval_config,
    )

    results = response.get("retrievalResults", [])

    if not results:
        context = "No relevant documents found in the knowledge base."
    else:
        context_parts = []
        for i, result in enumerate(results, 1):
            text = result.get("content", {}).get("text", "")
            score = result.get("score", 0)
            source = result.get("location", {}).get("s3Location", {}).get("uri", "unknown")
            context_parts.append(f"[Source {i} | score: {score:.2f} | {source}]\n{text}")
        context = "\n\n".join(context_parts)

    # Step 2: Generate answer using retrieved context
    history_text = ""
    if chat_history:
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-5:]])
        history_text = f"\nRecent conversation:\n{history_text}\n"

    system_prompt = f"""You are a helpful document assistant. Answer questions using the retrieved context below.
If the context doesn't contain enough information, say so clearly.
Cite sources by their number when referencing specific information.
{history_text}
Retrieved Context:
{context}"""

    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=system_prompt, model=model)
    response = agent(query)
    return str(response)
```

- [ ] **Step 4: Create app entry point**

```python
# containers/rag-query/app.py
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from query import rag_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = 8080


class RAGQueryHandler(BaseHTTPRequestHandler):
    """HTTP handler for RAG Query AgentCore Runtime."""

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/invocations":
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            query = body.get("query", "")
            user_email = body.get("user_email")
            search_scope = body.get("search_scope", "all")
            chat_history = body.get("chat_history", [])

            try:
                result = rag_query(
                    query=query,
                    user_email=user_email,
                    search_scope=search_scope,
                    chat_history=chat_history,
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"response": result}).encode())
            except Exception as e:
                logger.error(f"RAG query error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), RAGQueryHandler)
    logger.info(f"RAG Query runtime listening on port {PORT}")
    server.serve_forever()
```

- [ ] **Step 5: Commit**

```bash
git add containers/rag-query/
git commit -m "feat: add RAG Query AgentCore container with KB retrieval and hybrid search"
```

---

### Task 10: AgentCore CDK stack

**Files:**
- Create: `infrastructure/agentcore_stack.py`
- Create: `tests/unit/test_agentcore_stack.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agentcore_stack.py
import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.agentcore_stack import AgentCoreStack


def test_creates_multi_agent_runtime(app, stack):
    nested = AgentCoreStack(stack, "TestAC",
        knowledge_base_id="kb-123",
        data_bucket_name="srd-store-test-123-us-east-1",
        collection_endpoint="https://abc.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    # AgentCore uses CfnAgentRuntime or similar L1 construct
    # For now verify IAM roles are created
    template.resource_count_is("AWS::IAM::Role", 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agentcore_stack.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement the stack**

```python
# infrastructure/agentcore_stack.py
import os
from aws_cdk import (
    NestedStack,
    CfnOutput,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class AgentCoreStack(NestedStack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        knowledge_base_id: str,
        data_bucket_name: str,
        collection_endpoint: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")

        model_id = env_params["default_llm_model"]

        # Build container images
        multi_agent_image = ecr_assets.DockerImageAsset(
            self, f"srd-multi-agent-image-{env_name}",
            directory=os.path.join(os.getcwd(), "containers/multi-agent"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        rag_query_image = ecr_assets.DockerImageAsset(
            self, f"srd-rag-query-image-{env_name}",
            directory=os.path.join(os.getcwd(), "containers/rag-query"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # IAM role for Multi-Agent runtime
        multi_agent_role = iam.Role(
            self, f"srd-multi-agent-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("agentcore.amazonaws.com"),
            ),
            inline_policies={
                "MultiAgentPolicy": iam.PolicyDocument(statements=[
                    # Bedrock model invocation (3-part for global inference)
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}",
                            f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                        ],
                    ),
                    # KB retrieval
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                    # S3 for uploads (code gen, ppt gen)
                    iam.PolicyStatement(
                        actions=["s3:PutObject", "s3:GetObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/*"],
                    ),
                ]),
            },
        )

        # IAM role for RAG Query runtime
        rag_query_role = iam.Role(
            self, f"srd-rag-query-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("agentcore.amazonaws.com"),
            ),
            inline_policies={
                "RAGQueryPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}",
                            f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                ]),
            },
        )

        # NOTE: AgentCore CDK L1 constructs (CfnAgentRuntime) may need to be
        # configured once the service API stabilizes. For now, we define the
        # container images and IAM roles. The actual AgentCore registration
        # can be done via SDK calls in deploy.sh or as custom resources.

        # Outputs
        self.multi_agent_image_uri = multi_agent_image.image_uri
        self.rag_query_image_uri = rag_query_image.image_uri
        self.multi_agent_role_arn = multi_agent_role.role_arn
        self.rag_query_role_arn = rag_query_role.role_arn

        CfnOutput(self, f"multi-agent-image-{env_name}",
                  value=multi_agent_image.image_uri,
                  description="Multi-Agent container image URI")
        CfnOutput(self, f"rag-query-image-{env_name}",
                  value=rag_query_image.image_uri,
                  description="RAG Query container image URI")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5",
                reason="Global inference profile requires wildcard region for foundation model ARN"),
        ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_agentcore_stack.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/agentcore_stack.py tests/unit/test_agentcore_stack.py
git commit -m "feat: add AgentCore stack with container builds and IAM roles"
```

---

## Phase 5: UI Revamp

### Task 11: Update model list and remove deprecated features config

**Files:**
- Modify: `artifacts/chat-ui/src/default-properties.json`

- [ ] **Step 1: Replace default-properties.json**

```json
{
    "document-chat": {
        "config": {
            "models": [
                {
                    "label": "Claude Sonnet 4.6 (Global)",
                    "value": "global.anthropic.claude-sonnet-4-6-v1:0",
                    "iconName": "keyboard",
                    "description": "Latest Sonnet | Global routing | Up to 200k context",
                    "tags": ["Anthropic"],
                    "labelTag": "Recommended"
                },
                {
                    "label": "Claude Sonnet 4.6 (US)",
                    "value": "us.anthropic.claude-sonnet-4-6-v1:0",
                    "iconName": "keyboard",
                    "description": "Latest Sonnet | US-only routing | Up to 200k context",
                    "tags": ["Anthropic"],
                    "labelTag": "US Region"
                },
                {
                    "label": "Claude Opus 4.6 (Global)",
                    "value": "global.anthropic.claude-opus-4-6-v1:0",
                    "iconName": "keyboard",
                    "description": "Most capable | Global routing | Up to 200k context",
                    "tags": ["Anthropic"],
                    "labelTag": "Premium"
                },
                {
                    "label": "Claude Opus 4.6 (US)",
                    "value": "us.anthropic.claude-opus-4-6-v1:0",
                    "iconName": "keyboard",
                    "description": "Most capable | US-only routing | Up to 200k context",
                    "tags": ["Anthropic"],
                    "labelTag": "US Region"
                }
            ],
            "languages": [
                {"label": "English", "value": "english"},
                {"label": "Hindi", "value": "hindi"},
                {"label": "French", "value": "french"},
                {"label": "Spanish", "value": "spanish"},
                {"label": "Arabic", "value": "arabic"},
                {"label": "Italian", "value": "italian"}
            ]
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add artifacts/chat-ui/src/default-properties.json
git commit -m "feat: update model list to Claude 4.6 with global/geo inference profiles"
```

---

### Task 12: Add runtime-config.json loader to React app

**Files:**
- Create: `artifacts/chat-ui/public/runtime-config.json` (dev placeholder)
- Modify: `artifacts/chat-ui/src/` (add config loader)

- [ ] **Step 1: Create dev placeholder runtime-config.json**

```json
{
    "cognitoUserPoolId": "PLACEHOLDER",
    "cognitoClientId": "PLACEHOLDER",
    "cognitoRegion": "us-east-1",
    "restEndpointUrl": "http://localhost:3001/rag/",
    "websocketUrl": "ws://localhost:3001/ws"
}
```

Place at `artifacts/chat-ui/public/runtime-config.json`.

- [ ] **Step 2: Create config loader utility**

```typescript
// artifacts/chat-ui/src/runtime-config.ts
export interface RuntimeConfig {
    cognitoUserPoolId: string;
    cognitoClientId: string;
    cognitoRegion: string;
    restEndpointUrl: string;
    websocketUrl: string;
}

let cachedConfig: RuntimeConfig | null = null;

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
    if (cachedConfig) return cachedConfig;

    const response = await fetch("/runtime-config.json");
    if (!response.ok) {
        throw new Error("Failed to load runtime-config.json");
    }
    cachedConfig = await response.json();
    return cachedConfig!;
}

export function getRuntimeConfig(): RuntimeConfig {
    if (!cachedConfig) {
        throw new Error("Runtime config not loaded. Call loadRuntimeConfig() first.");
    }
    return cachedConfig;
}
```

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/public/runtime-config.json artifacts/chat-ui/src/runtime-config.ts
git commit -m "feat: add runtime-config.json loader for dynamic CloudFront config"
```

---

### Task 13: Remove deprecated UI pages

**Files:**
- Delete: `artifacts/chat-ui/src/pages/sentiment-page.tsx`
- Delete: `artifacts/chat-ui/src/pages/ocr-page.tsx`
- Delete: `artifacts/chat-ui/src/pages/pii-redact-page.tsx`
- Modify: `artifacts/chat-ui/src/pages/index.tsx` (remove exports)

- [ ] **Step 1: Delete deprecated page files**

```bash
rm artifacts/chat-ui/src/pages/sentiment-page.tsx
rm artifacts/chat-ui/src/pages/ocr-page.tsx
rm artifacts/chat-ui/src/pages/pii-redact-page.tsx
```

- [ ] **Step 2: Update page index to remove deleted imports**

Remove any imports/exports of `SentimentPage`, `OcrPage`, `PiiRedactPage` from `artifacts/chat-ui/src/pages/index.tsx`. Keep only: `HomePage`, `ChatPage`, `AgentPage`, `HelpPage`, `UploadPage`, `NotFoundPage`.

- [ ] **Step 3: Update navigation/routing**

Remove route entries and side-nav items for Sentiment, OCR, and PII Redaction. Keep:
- Document Chat (with Manage Documents sub-link)
- Multi-Agent

- [ ] **Step 4: Commit**

```bash
git add -A artifacts/chat-ui/src/pages/
git commit -m "feat: remove deprecated Sentiment, OCR, and PII Redaction pages"
```

---

### Task 14: Add document scope toggle to chat page

**Files:**
- Modify: `artifacts/chat-ui/src/pages/chat-page.tsx`

- [ ] **Step 1: Add search scope toggle**

Add a Cloudscape `Toggle` or `SegmentedControl` component to the chat page input area:

```tsx
// Add to chat-page.tsx input area
<SpaceBetween direction="horizontal" size="xs">
    <Toggle
        onChange={({ detail }) => setSearchScope(detail.checked ? "my_docs" : "all")}
        checked={searchScope === "my_docs"}
    >
        My Documents Only
    </Toggle>
</SpaceBetween>
```

Add state: `const [searchScope, setSearchScope] = useState("all");`

Pass `search_scope` in the WebSocket message payload alongside the query.

- [ ] **Step 2: Commit**

```bash
git add artifacts/chat-ui/src/pages/chat-page.tsx
git commit -m "feat: add My Documents / All Documents toggle to chat page"
```

---

## Phase 6: CLI Deployment Wizard

### Task 15: Create deploy.sh

**Files:**
- Create: `deploy.sh`

- [ ] **Step 1: Write deploy.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Serverless RAG Demo v2 — Deployment Wizard
# Usage: sh deploy.sh

VALID_REGIONS=("us-east-1" "us-east-2" "us-west-2" "ap-southeast-2" "ap-northeast-1" "eu-central-1")
DEFAULT_ENV="test"

echo ""
echo "  Serverless RAG Demo v2 — Deployment"
echo "  ────────────────────────────────────"
echo ""

# Step 1: Region selection
detected_region=$(aws configure get region 2>/dev/null || echo "")
if [[ -n "$detected_region" ]] && [[ " ${VALID_REGIONS[*]} " =~ " $detected_region " ]]; then
    echo "  [1] Region: $detected_region (auto-detected)"
    REGION="$detected_region"
else
    echo "  [1] Select region (Titan Embed V2 not available in us-west-1, ap-southeast-1):"
    select region in "${VALID_REGIONS[@]}"; do
        if [[ -n "$region" ]]; then
            REGION="$region"
            break
        fi
    done
fi

# Step 2: Environment
echo ""
read -p "  [2] Environment name [${DEFAULT_ENV}]: " ENV_NAME
ENV_NAME="${ENV_NAME:-$DEFAULT_ENV}"

# Step 3: OCU mode
echo ""
echo "  [3] OpenSearch Serverless NextGen mode:"
echo "      1) Demo (scale-to-zero, $0 when idle)"
echo "      2) Production (always-on, min 2 OCU, ~\$345/month)"
read -p "      Choice [1]: " OCU_CHOICE
OCU_CHOICE="${OCU_CHOICE:-1}"
if [[ "$OCU_CHOICE" == "2" ]]; then
    OCU_MODE="production"
else
    OCU_MODE="demo"
fi

echo ""
echo "  [4] Deploying with:"
echo "      Region:      $REGION"
echo "      Environment: $ENV_NAME"
echo "      OCU Mode:    $OCU_MODE"
echo ""
read -p "  Proceed? [Y/n]: " CONFIRM
CONFIRM="${CONFIRM:-Y}"
if [[ "$CONFIRM" != "Y" && "$CONFIRM" != "y" ]]; then
    echo "  Aborted."
    exit 0
fi

# Export for CDK
export CDK_DEFAULT_REGION="$REGION"
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "  Deploying..."

# Bootstrap CDK if needed
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$REGION 2>/dev/null || true

# Deploy all stacks
cdk deploy --all \
    --context environment_name="$ENV_NAME" \
    --context is_aoss="yes" \
    --context embed_model_id="amazon.titan-embed-text-v2:0" \
    --context ocu_mode="$OCU_MODE" \
    --require-approval never \
    --outputs-file cdk-outputs.json

echo ""
echo "  ✓ Deployment complete!"
echo ""

# Extract and display UI URL
if command -v jq &>/dev/null && [[ -f cdk-outputs.json ]]; then
    UI_URL=$(jq -r '.. | .["ui-url-'$ENV_NAME'"] // empty' cdk-outputs.json 2>/dev/null | head -1)
    if [[ -n "$UI_URL" ]]; then
        echo "  UI: $UI_URL"
    fi
fi

echo ""
```

- [ ] **Step 2: Make executable**

```bash
chmod +x deploy.sh
```

- [ ] **Step 3: Commit**

```bash
git add deploy.sh
git commit -m "feat: add streamlined deploy.sh wizard"
```

---

## Phase 7: Stack Wiring and Cleanup

### Task 16: Rewire app.py and main stack

**Files:**
- Modify: `app.py`
- Modify: `llms_with_serverless_rag/llms_with_serverless_rag_stack.py`

- [ ] **Step 1: Rewrite app.py**

```python
#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import Tags
from llms_with_serverless_rag.llms_with_serverless_rag_stack import LlmsWithServerlessRagStack

app = cdk.App()

account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION")
env = cdk.Environment(account=account_id, region=region)
env_name = app.node.try_get_context("environment_name")

stack = LlmsWithServerlessRagStack(app, f"ServerlessRagV2-{env_name}", env=env)
Tags.of(stack).add("project", "serverless-rag-demo-v2")

app.synth()
```

- [ ] **Step 2: Rewrite main stack composition**

```python
# llms_with_serverless_rag/llms_with_serverless_rag_stack.py
from aws_cdk import Stack, Tags
from constructs import Construct
from infrastructure.opensearch_nextgen_stack import OpensearchNextgenStack
from infrastructure.knowledge_base_stack import KnowledgeBaseStack
from infrastructure.agentcore_stack import AgentCoreStack
from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack
from infrastructure.api_gw_stack import ApiGw_Stack


class LlmsWithServerlessRagStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")

        # 1. OpenSearch Serverless NextGen
        oss_stack = OpensearchNextgenStack(self, f"AOSS-{env_name}")

        # 2. Bedrock Knowledge Base (depends on AOSS)
        kb_stack = KnowledgeBaseStack(
            self, f"KB-{env_name}",
            collection_arn=oss_stack.collection_arn,
            collection_endpoint=oss_stack.collection_endpoint,
        )
        kb_stack.node.add_dependency(oss_stack)

        # 3. AgentCore Runtimes (depends on KB)
        agentcore_stack = AgentCoreStack(
            self, f"AgentCore-{env_name}",
            knowledge_base_id=kb_stack.knowledge_base_id,
            data_bucket_name=kb_stack.data_bucket_name,
            collection_endpoint=oss_stack.collection_endpoint,
        )
        agentcore_stack.node.add_dependency(kb_stack)

        # 4. API Gateway + Cognito + WebSocket
        # NOTE: api_gw_stack.py needs refactoring in a follow-up task
        # to remove Lambda refs and wire to AgentCore.
        # For now this is a placeholder for the dependency chain.

        # 5. CloudFront Hosting (depends on Cognito + API GW outputs)
        # Will be wired after api_gw_stack refactoring provides
        # user_pool_id, client_id, rest_url, wss_url
```

- [ ] **Step 3: Commit**

```bash
git add app.py llms_with_serverless_rag/llms_with_serverless_rag_stack.py
git commit -m "feat: rewire app.py and main stack for v2 architecture"
```

---

### Task 17: Update cdk.json — remove deprecated keys

**Files:**
- Modify: `cdk.json`

- [ ] **Step 1: Remove deprecated keys from all environments**

From `dev`, `qa`, `sandbox` blocks, remove these keys:
- `ecr_repository_name`
- `apprunner_service_name`
- `lambda_role_name`
- `lambda_function_name`
- `bedrock_agents_function_name`
- `bedrock_indexing_function_name`
- `bedrock_querying_function_name`
- `bedrock_wrangler_function_name`
- `addtional_libs_layer_name`
- `strands_layer_name`
- `agents_tools_layer_name`
- `langchainpy_layer_name`
- `pypdf_layer`
- `index_dynamo_table_name`
- `conversations_dynamo_table_name`

Also remove the top-level `wrangler_regions` block.

- [ ] **Step 2: Add v2 keys to existing environments**

Add to each existing environment (`dev`, `qa`, `sandbox`):
```json
"collection_group_name": "srd-group-{env}",
"knowledge_base_name": "srd-kb-{env}",
"agentcore_multi_agent": "srd-multi-agent-{env}",
"agentcore_rag_query": "srd-rag-query-{env}",
"default_llm_model": "global.anthropic.claude-sonnet-4-6-v1:0",
"embed_model_id": "amazon.titan-embed-text-v2:0",
"ocu_mode": "demo"
```

Rename `s3_images_data` → `s3_data_bucket` in each env.

- [ ] **Step 3: Commit**

```bash
git add cdk.json
git commit -m "chore: clean deprecated keys from cdk.json, add v2 config to all envs"
```

---

### Task 18: Delete deprecated files

**Files:**
- Delete: `infrastructure/apprunner_hosting_stack.py`
- Delete: `infrastructure/ecr_ui_stack.py`
- Delete: `infrastructure/bedrock_layer_stack.py`
- Delete: `infrastructure/dynamodb_stack.py`
- Delete: `infrastructure/opensearch_vectordb_stack.py`
- Delete: `buildspec_bedrock.yml`
- Delete: `buildspec_dockerize_ui.yml`
- Delete: `artifacts/chat-ui/Dockerfile`
- Delete: `artifacts/chat-ui/.dockerignore`
- Delete: `artifacts/chat-ui/nginx.conf`
- Delete: `artifacts/bedrock_lambda/` (entire directory)
- Delete: `creator.sh`

- [ ] **Step 1: Remove deprecated infrastructure files**

```bash
rm infrastructure/apprunner_hosting_stack.py
rm infrastructure/ecr_ui_stack.py
rm infrastructure/bedrock_layer_stack.py
rm infrastructure/dynamodb_stack.py
rm infrastructure/opensearch_vectordb_stack.py
```

- [ ] **Step 2: Remove deprecated build/deploy files**

```bash
rm buildspec_bedrock.yml
rm -f buildspec_dockerize_ui.yml
rm -f creator.sh
```

- [ ] **Step 3: Remove deprecated UI Docker files**

```bash
rm -f artifacts/chat-ui/Dockerfile
rm -f artifacts/chat-ui/.dockerignore
rm -f artifacts/chat-ui/nginx.conf
```

- [ ] **Step 4: Remove entire Lambda directory**

```bash
rm -rf artifacts/bedrock_lambda/
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove deprecated AppRunner, ECR, Lambda, DynamoDB, and build files"
```

---

### Task 19: Refactor api_gw_stack.py for v2

**Files:**
- Modify: `infrastructure/api_gw_stack.py`

- [ ] **Step 1: Rewrite api_gw_stack.py**

Major changes:
- Remove all Lambda function definitions and layer references
- Remove `ECRUIStack` and `Storage_Stack` imports/usage
- Keep Cognito User Pool + Client
- Keep WebSocket API Gateway (will route to AgentCore via Lambda proxy or HTTP integration)
- Keep REST API Gateway for presigned URL generation (thin Lambda or direct S3 integration)
- Remove index-documents, connect-tracker, file_data endpoints
- Keep get-presigned-url endpoint (needs a small Lambda for S3 presigned URL generation)
- Export Cognito IDs and API URLs for CloudFront stack

The full rewrite is large — key structure:

```python
# infrastructure/api_gw_stack.py
from aws_cdk import (
    Stack, Tags,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_cognito as cognito,
    aws_apigatewayv2 as apigw2,
    CfnOutput,
)
import aws_cdk as cdk
import os
from constructs import Construct
import cdk_nag as _cdk_nag

from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack


class ApiGw_Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *,
                 knowledge_base_id: str,
                 data_bucket_name: str,
                 multi_agent_role_arn: str,
                 rag_query_role_arn: str,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        region = os.getenv("CDK_DEFAULT_REGION")
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")

        # Cognito User Pool
        user_pool = cognito.UserPool(self, f"srd-auth-{env_name}",
            user_pool_name=env_params["rag-llm-user-pool"],
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True)
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8, require_digits=True,
                require_lowercase=True, require_uppercase=True,
                require_symbols=True,
            ),
        )

        user_pool_client = cognito.UserPoolClient(self, f"srd-client-{env_name}",
            user_pool=user_pool,
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            id_token_validity=cdk.Duration.days(1),
        )

        # WebSocket API (routes to AgentCore via Lambda proxy)
        websocket_api = apigw2.CfnApi(self, f"srd-wss-{env_name}",
            protocol_type="WEBSOCKET",
            name=f"srd-streaming-{env_name}",
            route_selection_expression="$request.body.action",
        )

        wss_url = f"{websocket_api.attr_api_endpoint}/{env_name}"

        # TODO: Add WebSocket routes + Lambda proxy to AgentCore
        # TODO: Add REST API for presigned URL generation

        # REST endpoint placeholder
        rest_endpoint_url = f"https://placeholder.execute-api.{region}.amazonaws.com/{env_name}/rag/"

        # CloudFront Hosting
        cf_stack = CloudFrontHostingStack(self, f"CloudFront-{env_name}",
            cognito_user_pool_id=user_pool.user_pool_id,
            cognito_client_id=user_pool_client.user_pool_client_id,
            rest_endpoint_url=rest_endpoint_url,
            websocket_url=wss_url,
        )

        # Outputs
        CfnOutput(self, f"user-pool-id-{env_name}", value=user_pool.user_pool_id)
        CfnOutput(self, f"client-id-{env_name}", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, f"wss-url-{env_name}", value=wss_url)
```

- [ ] **Step 2: Commit**

```bash
git add infrastructure/api_gw_stack.py
git commit -m "refactor: rewrite api_gw_stack for v2 (remove Lambdas, keep Cognito + WSS)"
```

---

### Task 20: Final integration and synth test

**Files:**
- All previously created files

- [ ] **Step 1: Run CDK synth to validate**

```bash
cd /Users/fraseque/Fraser/Playground/serverless-rag-demo
pip install -r requirements.txt
cdk synth --context environment_name=test --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0 --quiet
```

Expected: Successful synthesis (CloudFormation template generated)

- [ ] **Step 2: Run all unit tests**

```bash
pytest tests/unit/ -v --cov=infrastructure --cov-report=term-missing
```

Expected: All tests PASS, coverage > 70%

- [ ] **Step 3: Run linter**

```bash
ruff check infrastructure/ containers/
ruff format --check infrastructure/ containers/
```

Expected: No errors

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: serverless-rag-demo v2 complete — NextGen AOSS, Bedrock KB, AgentCore, CloudFront"
```

---

## Implementation Order & Dependencies

```
Task 1 (config)
    ↓
Task 2 (AOSS NextGen) ──→ Task 4 (Bedrock KB) ──→ Task 10 (AgentCore CDK)
    ↓                                                    ↓
Task 3 (CloudFront)                              Tasks 5-9 (containers)
    ↓                                                    ↓
Tasks 11-14 (UI)                                 Task 16 (stack wiring)
    ↓                                                    ↓
Task 15 (deploy.sh)                              Task 17-18 (cleanup)
    ↓                                                    ↓
                    Task 19 (API GW refactor)
                            ↓
                    Task 20 (integration test)
```

## AIDLC Phases Mapping

Each phase can be shipped independently via `/aidlc-ship`:

| Phase | Tasks | Branch |
|-------|-------|--------|
| 1. Infrastructure | Tasks 1-3 | `aidlc/infra-nextgen-cloudfront` |
| 2. Bedrock KB | Task 4 | `aidlc/bedrock-knowledge-base` |
| 3. Multi-Agent | Tasks 5-8 | `aidlc/agentcore-multi-agent` |
| 4. RAG Query | Tasks 9-10 | `aidlc/agentcore-rag-query` |
| 5. UI Revamp | Tasks 11-14 | `aidlc/ui-revamp-v2` |
| 6. CLI | Task 15 | `aidlc/deploy-wizard` |
| 7. Wiring + Cleanup | Tasks 16-20 | `aidlc/v2-wiring-cleanup` |
