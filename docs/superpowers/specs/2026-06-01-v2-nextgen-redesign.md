# Serverless RAG Demo v2 — NextGen Redesign

**Date:** 2026-06-01
**Status:** Approved
**Scope:** Major version upgrade — hosting, vector DB, agents, models, CLI, UI

---

## 1. Summary

Upgrade the serverless-rag-demo project (220+ stars, 70 forks, launched 2023) to a modern 2026 architecture:

- **AppRunner → S3 + CloudFront** (AppRunner deprecated)
- **OpenSearch Serverless Classic → NextGen** (Collection Groups, scale-to-zero)
- **Lambda + Layers → Bedrock AgentCore Runtime** (for agent/query workloads)
- **Custom indexing Lambda → Bedrock Knowledge Base** (fully managed)
- **Claude 3.x → Claude 4.6** (Sonnet + Opus, global inference profiles)
- **Cohere Embed → Titan Embed Text V2** (native AWS, 1024 dims)
- **Flat orchestrator → Strands Graph pattern** (multi-agent)
- **5 Lambda layers → zero layers** (deps in containers)
- **Complex bash script → streamlined deploy wizard**
- **5 features → 2 focused features** (Document Chat + Multi-Agent)

LinkedIn headline: "Serverless RAG Demo now with Amazon OpenSearch Serverless v2 Collections"

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         CloudFront                                 │
│   Default behavior → S3 (React UI static build)                   │
│   + runtime-config.json (Cognito, API URLs)                       │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │      Cognito Auth       │
              └────────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐
  │  API GW     │  │  API GW     │  │  S3 Upload      │
  │  (WSS)      │  │  (REST)     │  │  (Presigned)    │
  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘
         │                 │                  │
         ▼                 ▼                  ▼
  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐
  │  AgentCore  │  │  AgentCore  │  │  Bedrock KB     │
  │  Runtime #1 │  │  Runtime #2 │  │  (auto-sync)    │
  │  Multi-Agent│  │  RAG Query  │  │  + Data Auto    │
  │  (Strands   │  │             │  │    parser       │
  │   Graph)    │  │             │  └────────┬────────┘
  └──────┬──────┘  └──────┬──────┘           │
         │                 │                  ▼
         │                 │         ┌─────────────────┐
         ▼                 ▼         │  OpenSearch     │
  ┌─────────────────────────────┐    │  Serverless     │
  │  Amazon Bedrock             │    │  NextGen        │
  │  Claude Sonnet/Opus 4.6     │    │  (VECTORSEARCH) │
  │  (Global inference profiles)│    └─────────────────┘
  └─────────────────────────────┘
```

---

## 3. Hosting: S3 + CloudFront

### Remove
- `infrastructure/apprunner_hosting_stack.py`
- `infrastructure/ecr_ui_stack.py`
- `buildspec_dockerize_ui.yml`
- `artifacts/chat-ui/Dockerfile`
- `artifacts/chat-ui/.dockerignore`
- `artifacts/chat-ui/nginx.conf`

### New: `CloudFrontHostingStack`
- S3 bucket (block public access, OAC)
- CloudFront distribution:
  - Default behavior → S3 origin
  - SPA routing: 403/404 → `/index.html` with 200
  - ViewerProtocolPolicy: REDIRECT_TO_HTTPS
  - CachePolicy: CACHING_OPTIMIZED
- `BucketDeployment` with inline Docker bundling (`node:20-slim`):
  - `npm ci && npm run build`
  - Outputs to S3
- Separate `runtime-config.json` source:
  ```json
  {
    "cognitoUserPoolId": "<from CDK>",
    "cognitoClientId": "<from CDK>",
    "cognitoRegion": "<region>",
    "restEndpointUrl": "<API GW REST URL>",
    "websocketUrl": "wss://<API GW WSS URL>"
  }
  ```
- React app loads `runtime-config.json` at startup (no build-time injection)

---

## 4. OpenSearch Serverless NextGen

### Replace `OpensearchVectorDbStack` with:

```python
# Collection Group (shared capacity)
CfnCollectionGroup(
    name="srd-group-{env}",
    standby_replicas="DISABLED",
    capacity_limits={
        "maxIndexingCapacityInOcu": max_index_ocu,
        "maxSearchCapacityInOcu": max_search_ocu,
        # min omitted for scale-to-zero (demo mode)
        # or set for production mode
    }
)

# Collection (references group)
CfnCollection(
    name="srd-vectors-{env}",
    type="VECTORSEARCH",
    collection_group_name="srd-group-{env}"
)
```

### Deployment modes (user picks during deploy):
- **Demo mode:** No min OCUs (scale-to-zero), max 4 each → $0 when idle
- **Production mode:** Min 2, max 10 each → always-on, ~$345/month minimum

### Index mapping (simplified for NextGen):
```json
{
  "settings": {"index": {"knn": true}},
  "mappings": {
    "properties": {
      "embedding": {"type": "knn_vector", "dimension": 1024}
    }
  }
}
```
- No `engine`, `method`, or `space_type` — NextGen auto-configures optimally
- Bedrock KB manages index creation automatically

### Security/Network/Data Access Policies
- Same pattern as current (encryption, network allow-from-public, data access for KB role + Lambda role)

---

## 5. Bedrock Knowledge Base (Replaces Indexing Lambda)

### Configuration:
- **Data source:** S3 bucket (auto-sync on upload)
- **Parser:** Amazon Bedrock Data Automation (extracts text + images from PDFs, handles tables/charts)
- **Chunking:** Semantic chunking (managed)
- **Embedding model:** Amazon Titan Embed Text V2 (`amazon.titan-embed-text-v2:0`, 1024 dims, normalized)
- **Vector store:** OpenSearch Serverless NextGen collection

### Per-user isolation via metadata filtering:
- Each uploaded file has a companion `.metadata.json`:
  ```json
  {"metadataAttributes": {"user_email": "user@example.com"}}
  ```
- UI provides toggle: "My Documents" vs "All Documents"
- **Pre-filter** (applied before hybrid search, not post-filter):
  - My Documents: `{"equals": {"key": "user_email", "value": "<cognito_email>"}}`
  - All Documents: no filter

### Hybrid search:
- Bedrock KB `Retrieve` API with `overrideSearchType: "HYBRID"`
- Native hybrid query (combined BM25 + KNN with proper score normalization)
- Replaces current two-query + client-side merge approach

### What's removed:
- Index Lambda
- DynamoDB tables (index tracking, conversations)
- CodeBuild for Lambda layers
- `langchain` / `langchain-text-splitters` dependency
- Custom chunking code
- Custom OCR extraction code

---

## 6. AgentCore Runtimes

### Runtime #1: Multi-Agent (Strands Graph)

**Container:** ARM64 Docker image with all deps (strands-agents, strands-agents-tools, python-pptx, Pillow, geopy, beautifulsoup4, xmltodict)

**Strands Graph pattern:**
```
┌─────────────┐
│  Classifier │ ← Entry node
└──────┬──────┘
       │ (conditional edges based on intent)
       ├──→ RetrieverNode (queries Bedrock KB Retrieve API)
       ├──→ WebSearchNode (DDG/Wiki/Yahoo → summarize)
       ├──→ CodeGenNode (generate HTML → S3 presigned URL)
       ├──→ PPTGenNode (generate slides → S3 presigned URL)
       ├──→ WeatherNode (geopy → weather data)
       └──→ GeneralNode (casual conversation)
```

- Shared state object across graph nodes (connection context, user info)
- Single utility module for S3 uploads / presigned URLs (no duplication)
- Streaming via AgentCore callback → WebSocket relay
- Model: Claude Sonnet 4.6 (global inference profile)

### Runtime #2: RAG Query

**Container:** Lightweight ARM64 image (strands-agents, boto3)

**Flow:**
1. Receive user query + chat history
2. Classify intent (retrieval vs casual)
3. If retrieval: call Bedrock KB `Retrieve` API with metadata filter + hybrid search
4. Augment prompt with retrieved context
5. Stream response via Claude Sonnet 4.6

### WebSocket Integration:
- API GW WebSocket → thin router (could be Lambda or AgentCore Gateway)
- Routes to appropriate AgentCore Runtime based on `behaviour` field
- AgentCore `InvokeAgentRuntime` with session ID for context

### What's eliminated:
- All Lambda layers (srd-core, srd-docs — deps in containers)
- CodeBuild for layers
- Lambda cold starts for agent workloads
- 250MB package limit workarounds

---

## 7. Models

### UI Model Selector:
```json
[
  {"label": "Claude Sonnet 4.6 (Global)", "value": "global.anthropic.claude-sonnet-4-6-v1:0"},
  {"label": "Claude Sonnet 4.6 (US)", "value": "us.anthropic.claude-sonnet-4-6-v1:0"},
  {"label": "Claude Opus 4.6 (Global)", "value": "global.anthropic.claude-opus-4-6-v1:0"},
  {"label": "Claude Opus 4.6 (US)", "value": "us.anthropic.claude-opus-4-6-v1:0"}
]
```

### Inference profiles:
- **Global** (`global.*`): Routes worldwide, highest throughput, ~10% cheaper
- **Geo US** (`us.*`): Routes within US regions only
- **Geo EU** (`eu.*`): Routes within EU regions only (for data residency)
- Configurable — users in EU can switch to EU profiles

### Embedding:
- Amazon Titan Embed Text V2 (`amazon.titan-embed-text-v2:0`)
- 1024 dimensions, normalized output
- Regional only (no cross-region support for embeddings)

### IAM Policy:
- 3-part IAM policy for global inference profiles (regional profile ARN + regional FM ARN + global FM ARN)

---

## 8. UI Revamp

### Features (v2):
- **Document Chat** — RAG with hybrid search, metadata filtering, file upload
- **Multi-Agent** — Strands Graph orchestrator (code gen, PPT, web search, weather, retrieval)

### Removed features:
- Sentiment Analysis (trivial with any LLM in 2026)
- OCR standalone page (folded into Document Chat — images auto-extracted during KB indexing)
- PII Redaction standalone page (not demo-worthy)

### UI changes:
- Side navigation: 2 items (Document Chat with Manage Documents sub-link, Multi-Agent)
- Homepage: Updated cards for 2 features only
- Document Chat: Add "My Documents / All Documents" toggle for search scope
- Model selector: Shows global/geo endpoint options
- Remove dead files: `chat-ui-input-panel-backup.tsx`, sentiment page, OCR page, PII page
- Load config from `runtime-config.json` (replace build-time env vars)

### Cleanup:
- Remove PII Redaction page + related images
- Remove Sentiment page + related images
- Remove OCR page (capability remains via KB parsing)
- Remove `help-properties.json` entries for removed pages

---

## 9. CLI Deployment (`deploy.sh`)

### Streamlined wizard:
```bash
$ sh deploy.sh

  Serverless RAG Demo v2 — Deployment
  ────────────────────────────────────
  [1] Region: us-east-1 (auto-detected)
      Or pick from: us-east-1, us-east-2, us-west-2, ap-southeast-2,
                    ap-northeast-1, eu-central-1
      (excludes us-west-1, ap-southeast-1 — no Titan Embed V2)

  [2] Environment: test

  [3] OpenSearch Serverless NextGen:
      > Demo mode (scale-to-zero)
        Production mode (always-on, min 2 OCU)

  [4] Deploying...
      ✓ OpenSearch Serverless NextGen
      ✓ Bedrock Knowledge Base
      ✓ AgentCore Runtimes (building containers...)
      ✓ Cognito
      ✓ API Gateway
      ✓ CloudFront + UI

  Done! UI: https://d1234abcd.cloudfront.net
```

### Key improvements:
- No CodeBuild polling loops (no Lambda layers to build)
- No ECR build for UI (BucketDeployment handles it)
- AgentCore container build via CDK (Docker bundling)
- Region fallback: selectable list if auto-detect fails
- CDK idempotency: only updates what changed
- Single `cdk deploy --all` (or sequential for dependencies)

### Region picker excludes:
- `us-west-1` (no Titan Embed V2)
- `ap-southeast-1` (no Titan Embed V2)

---

## 10. CDK Configuration (`cdk.json`)

### New `test` environment:
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

### Remove from cdk.json:
- `ecr_repository_name`
- `apprunner_service_name`
- `lambda_role_name`, `lambda_function_name`
- `bedrock_agents_function_name`, `bedrock_indexing_function_name`, `bedrock_querying_function_name`
- `bedrock_wrangler_function_name`
- `addtional_libs_layer_name`, `strands_layer_name`, `agents_tools_layer_name`
- `langchainpy_layer_name`, `pypdf_layer`
- `index_dynamo_table_name`, `conversations_dynamo_table_name`
- `wrangler_regions` (unused)

---

## 11. Files to Remove

### Infrastructure:
- `infrastructure/apprunner_hosting_stack.py`
- `infrastructure/ecr_ui_stack.py`
- `infrastructure/bedrock_layer_stack.py`
- `infrastructure/dynamodb_stack.py`
- `buildspec_dockerize_ui.yml`
- `buildspec_bedrock.yml`

### UI:
- `artifacts/chat-ui/Dockerfile`
- `artifacts/chat-ui/.dockerignore`
- `artifacts/chat-ui/nginx.conf`
- `artifacts/chat-ui/src/pages/sentiment-page.tsx`
- `artifacts/chat-ui/src/pages/ocr-page.tsx`
- `artifacts/chat-ui/src/pages/pii-redact-page.tsx`
- `artifacts/chat-ui/src/components/chat-ui/chat-ui-input-panel-backup.tsx`

### Lambda code (replaced by AgentCore + KB):
- `artifacts/bedrock_lambda/` (entire directory — logic moves to AgentCore containers)

### New directories:
- `containers/multi-agent/` (Dockerfile + Strands Graph code)
- `containers/rag-query/` (Dockerfile + RAG query code)
- `infrastructure/cloudfront_hosting_stack.py`
- `infrastructure/knowledge_base_stack.py`
- `infrastructure/agentcore_stack.py`
- `infrastructure/opensearch_nextgen_stack.py`

---

## 12. Dependencies

### Multi-Agent container (`containers/multi-agent/requirements.txt`):
```
strands-agents
strands-agents-tools
python-pptx
xmltodict
Pillow
geopy
beautifulsoup4
boto3
```

### RAG Query container (`containers/rag-query/requirements.txt`):
```
strands-agents
boto3
```

### CDK (`requirements.txt`):
```
aws-cdk-lib>=2.224.0
constructs>=10.0.0,<11.0.0
pyyaml>=6.0
cdk-nag>=2.10.0
```

### UI (`artifacts/chat-ui/package.json`):
- Keep existing Cloudscape + React 18 stack
- Remove any Docker-related configs

---

## 13. Security

- CloudFront serves static files publicly; app requires Cognito sign-in
- API Gateway validates Cognito tokens (REST authorizer + WSS $connect)
- AgentCore invocations authenticated via IAM (service-to-service)
- Global inference profiles require 3-part IAM policy
- Metadata filtering for per-user document isolation (pre-filter, not post-filter)
- Downgrade sensitive LOG.info to LOG.debug in agent code
- S3 bucket: block public access, OAC for CloudFront

---

## 14. Migration Notes

- Existing `dev`/`qa`/`sandbox` environments in cdk.json preserved but will need manual migration
- New `test` environment created for clean testing
- Users with existing AOSS Classic collections will need to create new NextGen collections (no in-place upgrade)
- Existing indexed data must be re-ingested via Bedrock KB
- PR #155 (spam) should be closed without merging

---

## 15. Development Workflow (AIDLC Plugin)

Use [Fraser27/aidlc-plugin](https://github.com/Fraser27/aidlc-plugin) for the full AI-driven development lifecycle.

### `.aidlc.yml` configuration:
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

### Implementation phases (each shipped via `/aidlc-ship`):
1. Infrastructure: AOSS NextGen + CloudFront + Cognito stacks
2. Bedrock KB: Knowledge Base stack + S3 data source
3. AgentCore: Multi-Agent runtime (Strands Graph container)
4. AgentCore: RAG Query runtime (container)
5. UI: Revamp (drop pages, add toggle, model selector, runtime-config)
6. CLI: New `deploy.sh` wizard
7. Cleanup: Remove deprecated files, update README

---

## 16. Success Criteria

- `sh deploy.sh` deploys entire stack in a single run without manual intervention
- UI accessible via CloudFront HTTPS URL with Cognito auth
- Document upload → auto-indexed by Bedrock KB → queryable within ~30 seconds
- "My Documents" / "All Documents" toggle works correctly
- Multi-Agent graph routes to correct specialist nodes
- Global inference profiles provide higher throughput
- Scale-to-zero: no cost when idle (demo mode)
- Clean, focused UI with 2 features
