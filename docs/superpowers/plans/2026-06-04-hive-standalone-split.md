# Hive Standalone Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Hive into a standalone open-source repo that deploys to any AWS account via a single `deploy.sh` command.

**Architecture:** Fresh repo with monorepo structure (backend/ + ui/ + infrastructure/). CDK creates Cognito, S3, KMS, CloudFront. Deploy script handles imperative AgentCore API calls. Auth via Amplify SDK → Identity Pool → SigV4.

**Tech Stack:** Python 3.12, Strands Agents, FastAPI, Node.js (Baileys sidecar), React 18, Cloudscape, Vite, AWS CDK (Python), AgentCore.

---

## File Map

| Directory | Purpose |
|-----------|---------|
| `backend/` | Copied from `containers/hive/` — app.py, hive_core/, sidecar/ |
| `backend/hive_core/` | Agents, channels, tools, guardrails, state, config |
| `ui/` | Standalone React app (from `artifacts/chat-ui/src/components/hive/` + auth) |
| `infrastructure/` | Single CDK stack: Cognito, S3, KMS, CloudFront, IAM |
| `docs/` | Architecture, channels, guardrails, adding-agents guides |
| Root | deploy.sh, config.yaml, app.py (CDK), README, LICENSE |

---

### Task 1: Initialize repo structure and backend

**Files:**
- Create: `hive/backend/` (copy from `containers/hive/`)
- Create: `hive/backend/Dockerfile`
- Create: `hive/backend/requirements.txt`
- Create: `hive/.gitignore`
- Create: `hive/LICENSE`

- [ ] **Step 1: Create repo directory and copy backend**

```bash
mkdir -p ~/Fraser/Playground/hive
cd ~/Fraser/Playground/hive
git init

# Copy backend
cp -r ~/Fraser/Playground/serverless-rag-demo/containers/hive/* backend/ 2>/dev/null
mkdir -p backend
cp ~/Fraser/Playground/serverless-rag-demo/containers/hive/app.py backend/
cp ~/Fraser/Playground/serverless-rag-demo/containers/hive/requirements.txt backend/
cp ~/Fraser/Playground/serverless-rag-demo/containers/hive/Dockerfile backend/
cp -r ~/Fraser/Playground/serverless-rag-demo/containers/hive/hive_core backend/
cp -r ~/Fraser/Playground/serverless-rag-demo/containers/hive/sidecar backend/
```

- [ ] **Step 2: Remove sidecar node_modules (will be installed at build time)**

```bash
rm -rf backend/sidecar/node_modules
```

- [ ] **Step 3: Create .gitignore**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# Node
node_modules/
dist/
build/

# CDK
cdk.out/
.cdk.staging/

# IDE
.idea/
.vscode/
*.swp

# AWS
cdk-outputs.json
config.yaml

# Env
.env
```

- [ ] **Step 4: Create LICENSE (Apache 2.0)**

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: initialize hive repo with backend from serverless-rag-demo"
```

---

### Task 2: Genericize backend (remove personal/hardcoded references)

**Files:**
- Modify: `backend/hive_core/guardrails.py` (refusal message)
- Modify: `backend/hive_core/agents/pa.py` (system prompt)
- Modify: `backend/hive_core/agents/base.py` (default model)
- Modify: `backend/hive_core/config.py` (naming)
- Modify: `backend/app.py` (remove srd references)

- [ ] **Step 1: Update default refusal message in guardrails.py**

Change line 89:
```python
# OLD:
"refusal_message": "I'm not able to do that on Fraser's behalf.",
# NEW:
"refusal_message": "I'm not authorized to do that.",
```

Also update `ExecutionContext` default at line 105:
```python
refusal_message: str = "I'm not authorized to do that."
```

- [ ] **Step 2: Genericize PA system prompt**

In `backend/hive_core/agents/pa.py`, replace the system prompt with:
```python
system_prompt=(
    "You are a personal AI assistant running on Hive. "
    "You can send and receive messages through configured channels (WhatsApp, Slack), "
    "read message history, manage contacts, and schedule reminders. "
    "Be helpful, concise, and respect the guardrails configured by your owner. "
    "When you don't know something, say so rather than guessing."
),
```

- [ ] **Step 3: Update default model ID**

In `backend/hive_core/agents/base.py`, find the default model parameter and change to:
```python
model_id: str = "global.anthropic.claude-sonnet-4-6-v1",
```

Search for any other hardcoded model references in the backend and update them to the same default.

- [ ] **Step 4: Remove srd-* naming from config.py**

In `backend/hive_core/config.py`, ensure no `srd-` prefixes remain. Any default names should use `hive-` prefix only.

- [ ] **Step 5: Verify no personal references remain**

```bash
grep -r "Fraser\|srd\|serverless-rag" backend/ --include="*.py" -l
```

Fix any remaining references.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: genericize backend — remove personal references, update defaults"
```

---

### Task 3: Create CDK infrastructure stack

**Files:**
- Create: `infrastructure/__init__.py`
- Create: `infrastructure/hive_stack.py`
- Create: `app.py` (CDK entry)
- Create: `cdk.json`
- Create: `requirements.txt` (CDK deps)

- [ ] **Step 1: Create CDK entry point**

Create `app.py` at repo root:
```python
#!/usr/bin/env python3
import os
import aws_cdk as cdk
from infrastructure.hive_stack import HiveStack

app = cdk.App()
stage = app.node.try_get_context("stage") or "prod"

HiveStack(
    app, f"Hive-{stage}",
    stage=stage,
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)

app.synth()
```

- [ ] **Step 2: Create cdk.json**

```json
{
  "app": "python3 app.py",
  "context": {
    "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": true,
    "@aws-cdk/aws-cloudfront:defaultSecurityPolicyTLSv1.2_2021": true
  }
}
```

- [ ] **Step 3: Create requirements.txt (CDK deps)**

```
aws-cdk-lib>=2.200.0
constructs>=10.0.0
```

- [ ] **Step 4: Create infrastructure/__init__.py**

```python
# Hive CDK infrastructure
```

- [ ] **Step 5: Create infrastructure/hive_stack.py**

```python
import os
from aws_cdk import (
    Stack, CfnOutput, RemovalPolicy, Duration,
    aws_s3 as s3,
    aws_kms as kms,
    aws_iam as iam,
    aws_cognito as cognito,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_ecr_assets as ecr_assets,
)
from constructs import Construct


class HiveStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, *, stage: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = self.account
        region = self.region

        # --- Cognito ---
        user_pool = cognito.UserPool(
            self, "HiveUserPool",
            user_pool_name=f"hive-{stage}",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8, require_lowercase=True,
                require_uppercase=True, require_digits=True,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        user_pool_client = user_pool.add_client(
            "HiveWebClient",
            user_pool_client_name=f"hive-web-{stage}",
            auth_flows=cognito.AuthFlow(
                user_password=True, user_srp=True,
            ),
        )

        identity_pool = cognito.CfnIdentityPool(
            self, "HiveIdentityPool",
            identity_pool_name=f"hive-{stage}",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=user_pool_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name,
                )
            ],
        )

        # Authenticated role for Identity Pool
        authenticated_role = iam.Role(
            self, "HiveCognitoAuthRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref,
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated",
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            inline_policies={
                "AgentCoreInvoke": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock-agentcore:InvokeAgentRuntime"],
                        resources=[f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/*"],
                    ),
                ]),
            },
        )

        cognito.CfnIdentityPoolRoleAttachment(
            self, "HiveIdentityPoolRoles",
            identity_pool_id=identity_pool.ref,
            roles={"authenticated": authenticated_role.role_arn},
        )

        # --- KMS ---
        hive_kms_key = kms.Key(
            self, "HiveKey",
            alias=f"hive-{stage}",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # --- S3 State Bucket ---
        state_bucket = s3.Bucket(
            self, "HiveStateBucket",
            bucket_name=f"hive-state-{account_id}-{region}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=hive_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # --- S3 UI Bucket + CloudFront ---
        ui_bucket = s3.Bucket(
            self, "HiveUIBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        oai = cloudfront.OriginAccessIdentity(self, "HiveOAI")
        ui_bucket.grant_read(oai)

        distribution = cloudfront.Distribution(
            self, "HiveDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(ui_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # --- IAM Role for AgentCore Runtime ---
        hive_role = iam.Role(
            self, "HiveRuntimeRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            ),
            inline_policies={
                "HivePolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "ecr:GetAuthorizationToken",
                            "ecr:BatchGetImage",
                            "ecr:GetDownloadUrlForLayer",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                        resources=[state_bucket.bucket_arn, f"{state_bucket.bucket_arn}/*"],
                    ),
                    iam.PolicyStatement(
                        actions=["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
                        resources=[hive_kms_key.key_arn],
                    ),
                    iam.PolicyStatement(
                        actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/*"],
                    ),
                ]),
            },
        )

        # --- Container Image ---
        hive_image = ecr_assets.DockerImageAsset(
            self, "HiveImage",
            directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # --- Outputs ---
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "IdentityPoolId", value=identity_pool.ref)
        CfnOutput(self, "HiveImageUri", value=hive_image.image_uri)
        CfnOutput(self, "HiveRoleArn", value=hive_role.role_arn)
        CfnOutput(self, "StateBucketName", value=state_bucket.bucket_name)
        CfnOutput(self, "KmsKeyId", value=hive_kms_key.key_id)
        CfnOutput(self, "UIBucketName", value=ui_bucket.bucket_name)
        CfnOutput(self, "CloudFrontUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "CloudFrontDistributionId", value=distribution.distribution_id)
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add CDK stack — Cognito, S3, KMS, CloudFront, IAM"
```

---

### Task 4: Create deploy.sh

**Files:**
- Create: `deploy.sh`

- [ ] **Step 1: Create deploy.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Hive — single-command deploy
# Usage: ./deploy.sh [destroy]

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info() { echo -e "${GREEN}[INFO]${RESET} $1"; }
warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
error() { echo -e "${RED}[ERROR]${RESET} $1"; exit 1; }

# --- Prerequisites ---
check_prereqs() {
    info "Checking prerequisites..."
    command -v aws >/dev/null 2>&1 || error "AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    command -v cdk >/dev/null 2>&1 || error "AWS CDK not found. Install: npm install -g aws-cdk"
    command -v docker >/dev/null 2>&1 || error "Docker not found. Install: https://docs.docker.com/get-docker/"
    command -v node >/dev/null 2>&1 || error "Node.js not found. Install: https://nodejs.org/"
    command -v python3 >/dev/null 2>&1 || error "Python 3 not found."

    # Check AWS credentials
    aws sts get-caller-identity >/dev/null 2>&1 || error "AWS credentials not configured. Run: aws configure"
    info "All prerequisites met."
}

# --- Configuration ---
configure() {
    if [[ -f config.yaml ]]; then
        REGION=$(grep "^region:" config.yaml | awk '{print $2}')
        STAGE=$(grep "^stage:" config.yaml | awk '{print $2}')
        info "Using existing config.yaml (region=$REGION, stage=$STAGE)"
    else
        echo -e "${BOLD}Hive Setup${RESET}"
        read -rp "AWS Region [us-east-1]: " REGION
        REGION=${REGION:-us-east-1}
        read -rp "Stage name [prod]: " STAGE
        STAGE=${STAGE:-prod}

        cat > config.yaml <<EOF
region: $REGION
stage: $STAGE
default_model: global.anthropic.claude-sonnet-4-6-v1
EOF
        info "Created config.yaml"
    fi

    export AWS_DEFAULT_REGION="$REGION"
    export CDK_DEFAULT_REGION="$REGION"
    export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    STACK_NAME="Hive-${STAGE}"
}

# --- CDK Deploy ---
deploy_cdk() {
    info "Deploying CDK stack: $STACK_NAME..."

    if [[ ! -d .venv ]]; then
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -q -r requirements.txt
    else
        source .venv/bin/activate
    fi

    cdk deploy "$STACK_NAME" \
        --context stage="$STAGE" \
        --outputs-file cdk-outputs.json \
        --require-approval never

    # Parse outputs
    IMAGE_URI=$(jq -r ".\"${STACK_NAME}\".HiveImageUri" cdk-outputs.json)
    ROLE_ARN=$(jq -r ".\"${STACK_NAME}\".HiveRoleArn" cdk-outputs.json)
    STATE_BUCKET=$(jq -r ".\"${STACK_NAME}\".StateBucketName" cdk-outputs.json)
    KMS_KEY_ID=$(jq -r ".\"${STACK_NAME}\".KmsKeyId" cdk-outputs.json)
    UI_BUCKET=$(jq -r ".\"${STACK_NAME}\".UIBucketName" cdk-outputs.json)
    CF_URL=$(jq -r ".\"${STACK_NAME}\".CloudFrontUrl" cdk-outputs.json)
    CF_DIST_ID=$(jq -r ".\"${STACK_NAME}\".CloudFrontDistributionId" cdk-outputs.json)
    USER_POOL_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolId" cdk-outputs.json)
    USER_POOL_CLIENT_ID=$(jq -r ".\"${STACK_NAME}\".UserPoolClientId" cdk-outputs.json)
    IDENTITY_POOL_ID=$(jq -r ".\"${STACK_NAME}\".IdentityPoolId" cdk-outputs.json)

    info "CDK stack deployed."
}

# --- AgentCore Runtime ---
deploy_runtime() {
    info "Deploying AgentCore runtime..."

    RUNTIME_NAME="hive-${STAGE}"
    ENV_VARS="{\"HIVE_STATE_BUCKET\":\"${STATE_BUCKET}\",\"HIVE_KMS_KEY_ID\":\"${KMS_KEY_ID}\"}"

    # Check if runtime exists
    RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes \
        --region "$REGION" \
        --query "agentRuntimeSummaries[?agentRuntimeName=='${RUNTIME_NAME}'].agentRuntimeArn | [0]" \
        --output text 2>/dev/null || echo "None")

    if [[ "$RUNTIME_ARN" == "None" || -z "$RUNTIME_ARN" ]]; then
        RUNTIME_ARN=$(aws bedrock-agentcore-control create-agent-runtime \
            --agent-runtime-name "$RUNTIME_NAME" \
            --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$IMAGE_URI\"}}" \
            --role-arn "$ROLE_ARN" \
            --network-configuration '{"networkMode":"PUBLIC"}' \
            --protocol-configuration '{"serverProtocol":"HTTP"}' \
            --lifecycle-configuration '{"idleRuntimeSessionTimeout":14400,"maxLifetime":28800}' \
            --environment-variables "$ENV_VARS" \
            --region "$REGION" \
            --query 'agentRuntimeArn' --output text)
        info "Runtime created: $RUNTIME_ARN"

        RUNTIME_ID=$(echo "$RUNTIME_ARN" | awk -F/ '{print $NF}')
        aws bedrock-agentcore-control create-agent-runtime-endpoint \
            --agent-runtime-id "$RUNTIME_ID" \
            --name "${RUNTIME_NAME}_endpoint" \
            --region "$REGION" > /dev/null
        info "Endpoint created."
    else
        RUNTIME_ID=$(echo "$RUNTIME_ARN" | awk -F/ '{print $NF}')
        aws bedrock-agentcore-control update-agent-runtime \
            --agent-runtime-id "$RUNTIME_ID" \
            --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$IMAGE_URI\"}}" \
            --role-arn "$ROLE_ARN" \
            --network-configuration '{"networkMode":"PUBLIC"}' \
            --lifecycle-configuration '{"idleRuntimeSessionTimeout":14400,"maxLifetime":28800}' \
            --environment-variables "$ENV_VARS" \
            --region "$REGION" > /dev/null 2>&1 || true
        info "Runtime updated: $RUNTIME_ARN"
    fi

    # Get endpoint URL
    ENDPOINT_URL=$(aws bedrock-agentcore-control list-agent-runtime-endpoints \
        --agent-runtime-id "$RUNTIME_ID" \
        --region "$REGION" \
        --query "agentRuntimeEndpointSummaries[0].agentRuntimeEndpointArn" \
        --output text 2>/dev/null || echo "")
}

# --- UI Build & Deploy ---
deploy_ui() {
    info "Building and deploying UI..."

    cd ui
    npm install --silent
    npm run build

    # Generate runtime-config.json
    cat > dist/runtime-config.json <<EOF
{
  "region": "$REGION",
  "userPoolId": "$USER_POOL_ID",
  "userPoolClientId": "$USER_POOL_CLIENT_ID",
  "identityPoolId": "$IDENTITY_POOL_ID",
  "hiveRuntimeId": "$RUNTIME_ID",
  "hiveRuntimeArn": "$RUNTIME_ARN"
}
EOF

    aws s3 sync dist/ "s3://${UI_BUCKET}/" --delete
    aws cloudfront create-invalidation \
        --distribution-id "$CF_DIST_ID" \
        --paths "/*" > /dev/null

    cd ..
    info "UI deployed."
}

# --- Destroy ---
destroy() {
    info "Destroying Hive stack..."
    source .venv/bin/activate 2>/dev/null || true

    STAGE=$(grep "^stage:" config.yaml | awk '{print $2}')
    STACK_NAME="Hive-${STAGE}"

    # Delete AgentCore runtime
    RUNTIME_NAME="hive-${STAGE}"
    RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes \
        --region "$REGION" \
        --query "agentRuntimeSummaries[?agentRuntimeName=='${RUNTIME_NAME}'].agentRuntimeArn | [0]" \
        --output text 2>/dev/null || echo "None")

    if [[ "$RUNTIME_ARN" != "None" && -n "$RUNTIME_ARN" ]]; then
        RUNTIME_ID=$(echo "$RUNTIME_ARN" | awk -F/ '{print $NF}')
        aws bedrock-agentcore-control delete-agent-runtime \
            --agent-runtime-id "$RUNTIME_ID" \
            --region "$REGION" 2>/dev/null || true
        info "Runtime deleted."
    fi

    cdk destroy "$STACK_NAME" --context stage="$STAGE" --force
    info "Stack destroyed."
}

# --- Main ---
main() {
    if [[ "${1:-}" == "destroy" ]]; then
        configure
        destroy
        exit 0
    fi

    check_prereqs
    configure
    deploy_cdk
    deploy_runtime
    deploy_ui

    echo ""
    echo -e "${BOLD}=== Hive Deployed ===${RESET}"
    echo -e "  UI:       ${GREEN}${CF_URL}${RESET}"
    echo -e "  Runtime:  ${RUNTIME_ID}"
    echo -e "  Region:   ${REGION}"
    echo -e "  Stage:    ${STAGE}"
    echo ""
    echo "  Create your first user account at the UI URL above."
}

main "$@"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x deploy.sh
```

- [ ] **Step 3: Commit**

```bash
git add deploy.sh
git commit -m "feat: add deploy.sh — single-command deploy wizard"
```

---

### Task 5: Create standalone UI app

**Files:**
- Create: `ui/package.json`
- Create: `ui/vite.config.ts`
- Create: `ui/tsconfig.json`
- Create: `ui/index.html`
- Create: `ui/src/main.tsx`
- Create: `ui/src/App.tsx`
- Create: `ui/src/auth/amplify-auth.ts`
- Copy: `ui/src/common/hive-ws.ts`
- Copy: `ui/src/components/` (all hive components)

- [ ] **Step 1: Create ui/package.json**

```json
{
  "name": "hive-ui",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@aws-amplify/ui-react": "^6.1.12",
    "@aws-crypto/sha256-js": "^5.2.0",
    "@aws-sdk/client-cognito-identity": "^3.750.0",
    "@aws-sdk/credential-providers": "^3.750.0",
    "@cloudscape-design/components": "^3.0.611",
    "@cloudscape-design/design-tokens": "^3.0.35",
    "@cloudscape-design/global-styles": "^1.0.27",
    "@smithy/protocol-http": "^4.1.0",
    "@smithy/signature-v4": "^4.1.0",
    "aws-amplify": "^6.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.55",
    "@types/react-dom": "^18.2.19",
    "@vitejs/plugin-react": "^4.7.0",
    "typescript": "^5.2.2",
    "vite": "^6.4.3"
  }
}
```

- [ ] **Step 2: Create ui/vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
  },
});
```

- [ ] **Step 3: Create ui/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create ui/index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Hive</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create ui/src/auth/amplify-auth.ts**

```typescript
import { Amplify } from "aws-amplify";
import { fetchAuthSession, signIn, signUp, signOut, confirmSignUp } from "aws-amplify/auth";

interface RuntimeConfig {
  region: string;
  userPoolId: string;
  userPoolClientId: string;
  identityPoolId: string;
  hiveRuntimeId: string;
  hiveRuntimeArn: string;
}

let runtimeConfig: RuntimeConfig | null = null;

export async function loadConfig(): Promise<RuntimeConfig> {
  if (runtimeConfig) return runtimeConfig;
  const res = await fetch("/runtime-config.json");
  runtimeConfig = await res.json();

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: runtimeConfig!.userPoolId,
        userPoolClientId: runtimeConfig!.userPoolClientId,
        identityPoolId: runtimeConfig!.identityPoolId,
      },
    },
  });

  return runtimeConfig!;
}

export async function getAwsCredentials() {
  const session = await fetchAuthSession();
  return session.credentials;
}

export { signIn, signUp, signOut, confirmSignUp, fetchAuthSession };
export type { RuntimeConfig };
```

- [ ] **Step 6: Create ui/src/main.tsx**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import "@cloudscape-design/global-styles/index.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 7: Create ui/src/App.tsx**

```typescript
import { useState, useEffect } from "react";
import { loadConfig, fetchAuthSession, signIn, signUp, confirmSignUp, signOut } from "./auth/amplify-auth";
import { HiveLayout } from "./components/hive-layout";
import { Container, Header, SpaceBetween, Input, Button, Box, Alert } from "@cloudscape-design/components";

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [authMode, setAuthMode] = useState<"login" | "signup" | "confirm">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      await loadConfig();
      try {
        const session = await fetchAuthSession();
        if (session.tokens) setAuthenticated(true);
      } catch {}
      setLoading(false);
    })();
  }, []);

  if (loading) return <Box textAlign="center" padding="xxl">Loading...</Box>;

  if (authenticated) {
    return <HiveLayout onSignOut={() => { signOut(); setAuthenticated(false); }} />;
  }

  const handleLogin = async () => {
    setError("");
    try {
      await signIn({ username: email, password });
      setAuthenticated(true);
    } catch (e: any) {
      setError(e.message || "Login failed");
    }
  };

  const handleSignup = async () => {
    setError("");
    try {
      await signUp({ username: email, password, options: { userAttributes: { email } } });
      setAuthMode("confirm");
    } catch (e: any) {
      setError(e.message || "Signup failed");
    }
  };

  const handleConfirm = async () => {
    setError("");
    try {
      await confirmSignUp({ username: email, confirmationCode: confirmCode });
      await signIn({ username: email, password });
      setAuthenticated(true);
    } catch (e: any) {
      setError(e.message || "Confirmation failed");
    }
  };

  return (
    <Box padding="xxl">
      <Container header={<Header variant="h1">Hive</Header>}>
        <SpaceBetween size="m">
          {error && <Alert type="error">{error}</Alert>}
          {authMode === "login" && (
            <SpaceBetween size="s">
              <Input placeholder="Email" value={email} onChange={({ detail }) => setEmail(detail.value)} />
              <Input placeholder="Password" type="password" value={password} onChange={({ detail }) => setPassword(detail.value)} />
              <Button variant="primary" onClick={handleLogin}>Sign In</Button>
              <Button variant="link" onClick={() => setAuthMode("signup")}>Create account</Button>
            </SpaceBetween>
          )}
          {authMode === "signup" && (
            <SpaceBetween size="s">
              <Input placeholder="Email" value={email} onChange={({ detail }) => setEmail(detail.value)} />
              <Input placeholder="Password" type="password" value={password} onChange={({ detail }) => setPassword(detail.value)} />
              <Button variant="primary" onClick={handleSignup}>Sign Up</Button>
              <Button variant="link" onClick={() => setAuthMode("login")}>Back to login</Button>
            </SpaceBetween>
          )}
          {authMode === "confirm" && (
            <SpaceBetween size="s">
              <Box>Check your email for a confirmation code.</Box>
              <Input placeholder="Confirmation code" value={confirmCode} onChange={({ detail }) => setConfirmCode(detail.value)} />
              <Button variant="primary" onClick={handleConfirm}>Confirm</Button>
            </SpaceBetween>
          )}
        </SpaceBetween>
      </Container>
    </Box>
  );
}
```

- [ ] **Step 8: Copy component files from source**

```bash
# Copy hive components
mkdir -p ui/src/components ui/src/common
cp ~/Fraser/Playground/serverless-rag-demo/artifacts/chat-ui/src/components/hive/*.tsx ui/src/components/
cp ~/Fraser/Playground/serverless-rag-demo/artifacts/chat-ui/src/components/hive/*.ts ui/src/components/
cp ~/Fraser/Playground/serverless-rag-demo/artifacts/chat-ui/src/common/hive-ws.ts ui/src/common/
```

- [ ] **Step 9: Update hive-layout.tsx imports**

In `ui/src/components/hive-layout.tsx`:
- Remove any `../../common/` prefix — change to `../common/`
- Remove any references to non-hive pages or routes
- Add `onSignOut` prop and a sign-out button in the header

- [ ] **Step 10: Update hive-ws.ts for SigV4 auth**

In `ui/src/common/hive-ws.ts`, update the WebSocket connection to use SigV4 signing from Amplify credentials instead of the previous auth mechanism. The connection URL comes from `runtime-config.json`.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: add standalone UI with Cognito auth and Cloudscape components"
```

---

### Task 6: Add model configuration to UI

**Files:**
- Modify: `ui/src/components/session-panel.tsx`
- Modify: `ui/src/components/types.ts`

- [ ] **Step 1: Add model field to AgentStatusInfo type**

In `ui/src/components/types.ts`, the `AgentStatusInfo` interface already has `model: string`. Add a new message type:
```typescript
| { type: "update_agent_model"; agent_id: string; model: string }
```

- [ ] **Step 2: Add "Edit Model" to agent actions dropdown in session-panel.tsx**

Add a new dropdown item `{ id: "edit_model", text: "Edit Model" }` to the ButtonDropdown items.

Add state for the model editor modal (similar to prompt editor):
```typescript
const [editingModel, setEditingModel] = useState<AgentStatusInfo | null>(null);
const [editModel, setEditModel] = useState("");
```

Add a Modal with an Input for the model ID.

- [ ] **Step 3: Add backend handler for update_agent_model**

In `backend/app.py`, add handler:
```python
elif msg_type == "update_agent_model" and session:
    agent_id = data.get("agent_id", "")
    new_model = data.get("model", "")
    if agent_id in session.registry.agents and new_model:
        agent = session.registry.agents[agent_id]
        agent.model_id = new_model
        agent._strands_agent = None  # Force re-init with new model
        await websocket.send_json({"type": "agents_status", "agents": session.registry.list_agents_info()})
```

- [ ] **Step 4: Wire onUpdateModel prop in hive-layout.tsx**

```typescript
onUpdateModel={(id, model) => {
    const ws = getHiveSocket();
    if (ws) sendHiveMessage(ws, { type: "update_agent_model", agent_id: id, model });
}}
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add per-agent model configuration in UI"
```

---

### Task 7: Documentation

**Files:**
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/channels.md`
- Create: `docs/guardrails.md`
- Create: `docs/adding-agents.md`

- [ ] **Step 1: Create README.md**

```markdown
# Hive

A multi-agent AI platform that connects to your communication channels (WhatsApp, Slack, MCP) and acts as your personal AI assistant. Deploy to your own AWS account with a single command.

## Architecture

- **Backend**: Python (Strands Agents + FastAPI) running on AWS Bedrock AgentCore
- **Channels**: WhatsApp (Baileys sidecar), Slack (Socket Mode), MCP servers
- **UI**: React + Cloudscape, hosted on CloudFront
- **Auth**: Cognito (email/password)
- **State**: S3 (encrypted with KMS)

## Prerequisites

- AWS CLI configured with credentials
- AWS CDK (`npm install -g aws-cdk`)
- Docker
- Node.js 20+
- Python 3.12+
- Access to [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)

## Quick Start

```bash
git clone https://github.com/your-org/hive.git
cd hive
./deploy.sh
```

The deploy script will:
1. Ask for your AWS region and stage name
2. Deploy infrastructure (Cognito, S3, KMS, CloudFront)
3. Build and push the backend container
4. Create/update the AgentCore runtime
5. Build and deploy the UI

Once complete, open the CloudFront URL and create your account.

## Features

- **Multi-Agent**: Personal Assistant, Reminder, Market agents (+ custom agents via UI)
- **Channels**: WhatsApp, Slack, MCP — all with real-time message feed
- **Guardrails**: Per-sender security tiers (owner/trusted/known/unknown)
- **Persona**: Configurable AI personality injected into all agents
- **Scheduler**: Recurring reminders and scheduled tasks
- **Agent Lifecycle**: Stop/start/restart agents, edit prompts and models live

## Configuration

After first deploy, edit `config.yaml`:

```yaml
region: us-east-1
stage: prod
default_model: global.anthropic.claude-sonnet-4-6-v1
```

## Teardown

```bash
./deploy.sh destroy
```

## Documentation

- [Architecture](docs/architecture.md)
- [Channels](docs/channels.md)
- [Guardrails](docs/guardrails.md)
- [Adding Agents](docs/adding-agents.md)

## License

Apache 2.0
```

- [ ] **Step 2: Create docs/architecture.md**

Document the system architecture: AgentCore runtime, WebSocket protocol, agent bus, channel manager, state persistence. Include a text diagram showing the data flow from UI → AgentCore → Backend → Channels.

- [ ] **Step 3: Create docs/channels.md**

Document each channel: WhatsApp (sidecar, QR pairing, LID handling, S3 auth persistence), Slack (bot token, socket mode), MCP (server connection, tool bridging). Include setup instructions for each.

- [ ] **Step 4: Create docs/guardrails.md**

Document the guardrails system: tier definitions (owner/trusted/known/unknown), policy actions, how enforcement works (prompt injection + hard gate), how to configure via UI.

- [ ] **Step 5: Create docs/adding-agents.md**

Document how to add custom agents: via UI (name, prompt, model) and via code (extending HiveAgent, registering tools, subscribing to bus).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: add README and documentation"
```

---

### Task 8: Final cleanup and verification

**Files:**
- Verify: all files in repo
- Test: `deploy.sh` dry-run logic
- Test: UI builds cleanly

- [ ] **Step 1: Verify no source repo references remain**

```bash
grep -r "serverless-rag-demo\|srd-\|Fraser" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.sh" .
```

Fix any remaining references.

- [ ] **Step 2: Verify backend Dockerfile builds**

```bash
cd backend && docker build --platform linux/arm64 -t hive-local . && cd ..
```

- [ ] **Step 3: Verify UI builds**

```bash
cd ui && npm install && npm run build && cd ..
```

- [ ] **Step 4: Verify CDK synthesizes**

```bash
source .venv/bin/activate
pip install -r requirements.txt
cdk synth Hive-prod --context stage=prod
```

- [ ] **Step 5: Final commit and tag**

```bash
git add -A
git commit -m "chore: final cleanup — verify all builds pass"
git tag v0.1.0
```

---

## Summary

| Task | Description | Estimated Steps |
|------|-------------|-----------------|
| 1 | Initialize repo + copy backend | 5 |
| 2 | Genericize backend | 6 |
| 3 | CDK infrastructure stack | 6 |
| 4 | Deploy script | 3 |
| 5 | Standalone UI app | 11 |
| 6 | Model config in UI | 5 |
| 7 | Documentation | 6 |
| 8 | Final cleanup + verification | 5 |
| **Total** | | **47 steps** |
