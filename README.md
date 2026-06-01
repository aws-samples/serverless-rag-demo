# Serverless RAG Demo v2

Scalable RAG and Multi-Agent workflows powered by Amazon Bedrock, OpenSearch Serverless NextGen, and Bedrock AgentCore.

## Features

- **Document Chat** — Upload documents, ask questions with hybrid search (BM25 + KNN), per-user document isolation
- **Multi-Agent** — Strands Graph orchestrator with specialist nodes: code generation, presentations, web search, weather, retrieval

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         CloudFront                                │
│   Default behavior → S3 (React UI static build)                  │
│   + runtime-config.json (Cognito, API URLs)                      │
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
         ▼                 ▼         ┌─────────────────┐
  ┌─────────────────────────────┐    │  OpenSearch     │
  │  Amazon Bedrock             │    │  Serverless     │
  │  Claude Sonnet/Opus 4.6     │    │  NextGen        │
  │  (Global inference profiles)│    │  (VECTORSEARCH) │
  └─────────────────────────────┘    └─────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Hosting | S3 + CloudFront (OAC) |
| Auth | Amazon Cognito |
| Vector DB | OpenSearch Serverless NextGen (scale-to-zero) |
| Indexing | Bedrock Knowledge Base + Data Automation parser |
| Embeddings | Amazon Titan Embed Text V2 (1024 dims) |
| LLM | Claude Sonnet 4.6 / Opus 4.6 (global inference profiles) |
| Agents | Bedrock AgentCore Runtimes (ARM64 containers) |
| Multi-Agent | Strands Graph pattern (classifier → specialist nodes) |
| IaC | AWS CDK (Python) |
| UI | React 18 + Cloudscape |

## Prerequisites

- An AWS account with Bedrock model access enabled for:
  - Claude Sonnet 4.6 / Opus 4.6
  - Amazon Titan Embed Text V2
- AWS CLI configured
- Python 3.12+
- Node.js 20+
- Docker (for container builds)
- AWS CDK CLI (`npm install -g aws-cdk`)

## Deployment

```bash
git clone https://github.com/aws-samples/serverless-rag-demo.git
cd serverless-rag-demo
sh deploy.sh
```

The wizard guides you through:

1. **Region** — auto-detected or pick from supported list
2. **Environment** — name for your deployment (default: `test`)
3. **OCU Mode** — Demo (scale-to-zero, $0 idle) or Production (always-on)

Deployment runs a single `cdk deploy --all` and outputs the CloudFront URL when complete.

### Supported Regions

| Region | Notes |
|--------|-------|
| us-east-1 | Recommended |
| us-east-2 | |
| us-west-2 | |
| ap-southeast-2 | |
| ap-northeast-1 | |
| eu-central-1 | |

> us-west-1 and ap-southeast-1 are excluded (no Titan Embed V2 support).

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest tests/unit/ -v

# Synthesize CloudFormation
cdk synth --context environment_name=test --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0

# Deploy
cdk deploy --all --context environment_name=test --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0
```

## Project Structure

```
├── infrastructure/                 # CDK stacks
│   ├── opensearch_nextgen_stack.py   # AOSS NextGen collection
│   ├── knowledge_base_stack.py       # Bedrock KB + S3 data source
│   ├── agentcore_stack.py            # AgentCore container builds + IAM
│   ├── cloudfront_hosting_stack.py   # S3 + CloudFront + runtime-config
│   └── api_gw_stack.py               # Cognito + API Gateway + WebSocket
├── containers/
│   ├── multi-agent/                # Strands Graph multi-agent runtime
│   │   ├── app.py                    # HTTP server (/ping, /invocations)
│   │   ├── graph.py                  # Graph: classify → route → execute
│   │   └── nodes/                    # Specialist nodes
│   └── rag-query/                  # RAG query runtime
│       ├── app.py                    # HTTP server
│       └── query.py                  # KB retrieval + response generation
├── artifacts/chat-ui/              # React + Cloudscape UI
├── tests/unit/                     # CDK unit tests
├── deploy.sh                       # Deployment wizard
├── app.py                          # CDK app entry point
└── cdk.json                        # CDK context and environment config
```

## License

MIT-0
