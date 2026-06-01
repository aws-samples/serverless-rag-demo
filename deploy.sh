#!/usr/bin/env bash
set -euo pipefail

# Serverless RAG Demo v2 — Deployment Wizard

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
echo "      1) Demo (scale-to-zero, \$0 when idle)"
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
DEPLOYER_ARN=$(aws sts get-caller-identity --query Arn --output text)

echo ""
echo "  Deploying..."

# Bootstrap CDK if needed
cdk bootstrap "aws://$CDK_DEFAULT_ACCOUNT/$REGION" 2>/dev/null || true

CDK_CONTEXT="--context environment_name=$ENV_NAME --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0 --context ocu_mode=$OCU_MODE --context deployer_arn=$DEPLOYER_ARN"

# Step A: Deploy AOSS collection
echo "  [A] Deploying OpenSearch Serverless collection..."
cdk deploy "SRD-AOSS-$ENV_NAME" $CDK_CONTEXT --require-approval never --outputs-file cdk-outputs.json

# Step B: Create AOSS index via Lambda (role is pre-authorized in data access policy)
echo "  [B] Creating vector index..."
INDEX_NAME=$(python3 -c "import json; d=json.load(open('cdk.json')); print(d['context']['$ENV_NAME']['index_name'])")
LAMBDA_NAME="srd-index-creator-$ENV_NAME"
PAYLOAD=$(printf '{"IndexName": "%s", "VectorDimensions": "1024"}' "$INDEX_NAME")
RESULT=$(aws lambda invoke --function-name "$LAMBDA_NAME" --payload "$PAYLOAD" --cli-binary-format raw-in-base64-out /dev/stdout --region "$REGION" 2>/dev/null | head -1)
echo "  Index creation result: $RESULT"
if echo "$RESULT" | grep -q '"status": "ERROR"'; then
    echo "  Index creation failed. Retrying in 30s..."
    sleep 30
    RESULT=$(aws lambda invoke --function-name "$LAMBDA_NAME" --payload "$PAYLOAD" --cli-binary-format raw-in-base64-out /dev/stdout --region "$REGION" 2>/dev/null | head -1)
    echo "  Retry result: $RESULT"
fi

# Step C: Deploy remaining CDK stacks (KB, Auth, CloudFront)
echo "  [C] Deploying Knowledge Base, Auth, and CloudFront..."
cdk deploy --all $CDK_CONTEXT --require-approval never --outputs-file cdk-outputs.json

# Step D: Deploy AgentCore Runtimes
echo "  [D] Deploying AgentCore Runtimes..."

# Extract Cognito values from CDK outputs
COGNITO_POOL_ID=$(jq -r ".[\"SRD-Auth-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"user-pool-id\")) | .value" cdk-outputs.json)
COGNITO_CLIENT_ID=$(jq -r ".[\"SRD-Auth-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"client-id\")) | .value" cdk-outputs.json)
COGNITO_IDENTITY_POOL_ID=$(jq -r ".[\"SRD-Auth-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"identity-pool-id\")) | .value" cdk-outputs.json)
EVAL_ROLE_ARN=$(jq -r ".[\"SRD-Auth-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"eval-role-arn\")) | .value" cdk-outputs.json)

# Get Knowledge Base values from CDK outputs
KB_ID=$(jq -r ".[\"SRD-KB-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"kb-id\")) | .value" cdk-outputs.json)
DATA_BUCKET=$(jq -r ".[\"SRD-KB-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"data-bucket\")) | .value" cdk-outputs.json)
DATA_SOURCE_ID=$(jq -r ".[\"SRD-KB-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"data-source-id\")) | .value" cdk-outputs.json)

# Get ECR image URIs from CDK outputs
RAG_IMAGE=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"rag-query-image\")) | .value" cdk-outputs.json)
MULTI_AGENT_IMAGE=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"multi-agent-image\")) | .value" cdk-outputs.json)

# Get IAM role ARNs
RAG_ROLE_ARN=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"rag-query-role\")) | .value" cdk-outputs.json 2>/dev/null || echo "")
MULTI_AGENT_ROLE_ARN=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"multi-agent-role\")) | .value" cdk-outputs.json 2>/dev/null || echo "")

# Environment variables for containers (dynamically extracted from CDK outputs)
RUNTIME_ENV_VARS="{\"KNOWLEDGE_BASE_ID\":\"$KB_ID\",\"REGION\":\"$REGION\",\"MODEL_ID\":\"global.anthropic.claude-opus-4-6-v1\"}"

# Helper: deploy a single AgentCore runtime (idempotent — creates or updates)
# Prints the runtime ARN to stdout; logs to stderr
deploy_runtime() {
    local RUNTIME_NAME="$1"
    local IMAGE_URI="$2"
    local ROLE_ARN="$3"
    local LABEL="$4"

    echo "  [D] $LABEL..." >&2

    # Check if runtime already exists
    local RUNTIME_ARN
    RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
        --query "agentRuntimeSummaries[?agentRuntimeName=='$RUNTIME_NAME'].agentRuntimeArn | [0]" --output text 2>/dev/null || echo "None")

    if [[ "$RUNTIME_ARN" == "None" || -z "$RUNTIME_ARN" ]]; then
        # Create new runtime (SigV4 auth — browser uses Identity Pool for temp creds)
        RUNTIME_ARN=$(aws bedrock-agentcore-control create-agent-runtime \
            --agent-runtime-name "$RUNTIME_NAME" \
            --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$IMAGE_URI\"}}" \
            --role-arn "$ROLE_ARN" \
            --network-configuration '{"networkMode":"PUBLIC"}' \
            --protocol-configuration '{"serverProtocol":"HTTP"}' \
            --environment-variables "$RUNTIME_ENV_VARS" \
            --region "$REGION" \
            --query 'agentRuntimeArn' --output text)
        echo "      Created: $RUNTIME_ARN" >&2

        # Create endpoint
        local RUNTIME_ID
        RUNTIME_ID=$(echo "$RUNTIME_ARN" | awk -F/ '{print $NF}')
        aws bedrock-agentcore-control create-agent-runtime-endpoint \
            --agent-runtime-id "$RUNTIME_ID" \
            --name "${RUNTIME_NAME}-endpoint" \
            --region "$REGION" > /dev/null
        echo "      Endpoint created" >&2
    else
        # Update existing runtime with new container image and env vars
        local RUNTIME_ID
        RUNTIME_ID=$(echo "$RUNTIME_ARN" | awk -F/ '{print $NF}')
        aws bedrock-agentcore-control update-agent-runtime \
            --agent-runtime-id "$RUNTIME_ID" \
            --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$IMAGE_URI\"}}" \
            --role-arn "$ROLE_ARN" \
            --network-configuration '{"networkMode":"PUBLIC"}' \
            --environment-variables "$RUNTIME_ENV_VARS" \
            --region "$REGION" > /dev/null 2>&1 || true
        echo "      Updated: $RUNTIME_ARN (new image deployed)" >&2
    fi

    # Return the ARN via stdout
    echo "$RUNTIME_ARN"
}

# Deploy RAG Query runtime
RAG_RUNTIME_NAME="srd_rag_query_${ENV_NAME}"
RAG_RUNTIME_ARN=$(deploy_runtime "$RAG_RUNTIME_NAME" "$RAG_IMAGE" "$RAG_ROLE_ARN" "RAG Query runtime")

# Deploy Multi-Agent runtime
MA_RUNTIME_NAME="srd_multi_agent_${ENV_NAME}"
MA_RUNTIME_ARN=$(deploy_runtime "$MA_RUNTIME_NAME" "$MULTI_AGENT_IMAGE" "$MULTI_AGENT_ROLE_ARN" "Multi-Agent runtime")

# Create CloudWatch log groups for runtimes (AgentCore doesn't auto-create these)
RAG_RUNTIME_ID=$(echo "$RAG_RUNTIME_ARN" | awk -F/ '{print $NF}')
MA_RUNTIME_ID=$(echo "$MA_RUNTIME_ARN" | awk -F/ '{print $NF}')
for LG_SUFFIX in "${RAG_RUNTIME_NAME}_endpoint" "DEFAULT"; do
    aws logs create-log-group --log-group-name "/aws/bedrock-agentcore/runtimes/${RAG_RUNTIME_ID}-${LG_SUFFIX}" --region "$REGION" 2>/dev/null || true
done
for LG_SUFFIX in "${MA_RUNTIME_NAME}_endpoint" "DEFAULT"; do
    aws logs create-log-group --log-group-name "/aws/bedrock-agentcore/runtimes/${MA_RUNTIME_ID}-${LG_SUFFIX}" --region "$REGION" 2>/dev/null || true
done
echo "      Log groups created" >&2

# Step E: Update runtime-config.json with AgentCore Runtime ARNs
echo "  [E] Updating runtime-config.json..."

# Get the UI bucket name
UI_BUCKET=$(jq -r ".[\"SRD-CloudFront-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"ui-url\")) | .value" cdk-outputs.json 2>/dev/null | head -1)
UI_BUCKET_NAME=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'srduibucket')].Name | [0]" --output text)

# Write updated runtime-config.json to S3
cat <<RCEOF | aws s3 cp - "s3://${UI_BUCKET_NAME}/runtime-config.json" --content-type application/json
{
  "cognitoUserPoolId": "$COGNITO_POOL_ID",
  "cognitoClientId": "$COGNITO_CLIENT_ID",
  "cognitoIdentityPoolId": "$COGNITO_IDENTITY_POOL_ID",
  "cognitoRegion": "$REGION",
  "ragRuntimeArn": "$RAG_RUNTIME_ARN",
  "multiAgentRuntimeArn": "$MA_RUNTIME_ARN",
  "dataBucketName": "$DATA_BUCKET",
  "knowledgeBaseId": "$KB_ID",
  "dataSourceId": "$DATA_SOURCE_ID",
  "evalRoleArn": "$EVAL_ROLE_ARN"
}
RCEOF
echo "  Updated runtime-config.json with AgentCore endpoints"

# Invalidate CloudFront cache
CF_DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?contains(Origins.Items[0].DomainName, 'srduibucket')].Id | [0]" --output text 2>/dev/null || echo "")
if [[ -n "$CF_DIST_ID" && "$CF_DIST_ID" != "None" ]]; then
    aws cloudfront create-invalidation --distribution-id "$CF_DIST_ID" --paths "/runtime-config.json" > /dev/null 2>&1 || true
fi

echo ""
echo "  Deployment complete!"
echo ""

# Display summary
if command -v jq &>/dev/null && [[ -f cdk-outputs.json ]]; then
    UI_URL=$(jq -r '.. | objects | to_entries[] | select(.key | contains("ui-url")) | .value' cdk-outputs.json 2>/dev/null | head -1)
    if [[ -n "$UI_URL" ]]; then
        echo "  UI:              $UI_URL"
    fi
fi
echo "  RAG Runtime:     $RAG_RUNTIME_ARN"
echo "  Agent Runtime:   $MA_RUNTIME_ARN"
echo ""
