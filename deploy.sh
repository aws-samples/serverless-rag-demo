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
DISCOVERY_URL="https://cognito-idp.${REGION}.amazonaws.com/${COGNITO_POOL_ID}/.well-known/openid-configuration"

# Get ECR image URIs from CDK outputs
RAG_IMAGE=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"rag-query-image\")) | .value" cdk-outputs.json)
MULTI_AGENT_IMAGE=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"multi-agent-image\")) | .value" cdk-outputs.json)

# Get IAM role ARNs
RAG_ROLE_ARN=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"rag-query-role\")) | .value" cdk-outputs.json 2>/dev/null || echo "")
MULTI_AGENT_ROLE_ARN=$(jq -r ".[\"SRD-AgentCore-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"multi-agent-role\")) | .value" cdk-outputs.json 2>/dev/null || echo "")

# Create or update RAG Query runtime
echo "  [D1] RAG Query runtime..."
RAG_RUNTIME_NAME="srd-rag-query-$ENV_NAME"
RAG_RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
    --query "agentRuntimeSummaries[?agentRuntimeName=='$RAG_RUNTIME_NAME'].agentRuntimeArn | [0]" --output text 2>/dev/null || echo "None")

if [[ "$RAG_RUNTIME_ARN" == "None" || -z "$RAG_RUNTIME_ARN" ]]; then
    RAG_RUNTIME_ARN=$(aws bedrock-agentcore-control create-agent-runtime \
        --agent-runtime-name "$RAG_RUNTIME_NAME" \
        --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$RAG_IMAGE\"}}" \
        --role-arn "$RAG_ROLE_ARN" \
        --network-configuration '{"networkMode":"PUBLIC"}' \
        --authorizer-configuration "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_CLIENT_ID\"]}}" \
        --protocol-configuration '{"serverProtocol":"HTTP"}' \
        --region "$REGION" \
        --query 'agentRuntimeArn' --output text)
    echo "  Created runtime: $RAG_RUNTIME_ARN"

    # Create endpoint
    aws bedrock-agentcore-control create-agent-runtime-endpoint \
        --agent-runtime-id "$(echo $RAG_RUNTIME_ARN | awk -F/ '{print $NF}')" \
        --name "${RAG_RUNTIME_NAME}-endpoint" \
        --region "$REGION" > /dev/null
    echo "  Created endpoint for RAG Query"
else
    echo "  RAG Query runtime already exists: $RAG_RUNTIME_ARN"
fi

# Create or update Multi-Agent runtime
echo "  [D2] Multi-Agent runtime..."
MA_RUNTIME_NAME="srd-multi-agent-$ENV_NAME"
MA_RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
    --query "agentRuntimeSummaries[?agentRuntimeName=='$MA_RUNTIME_NAME'].agentRuntimeArn | [0]" --output text 2>/dev/null || echo "None")

if [[ "$MA_RUNTIME_ARN" == "None" || -z "$MA_RUNTIME_ARN" ]]; then
    MA_RUNTIME_ARN=$(aws bedrock-agentcore-control create-agent-runtime \
        --agent-runtime-name "$MA_RUNTIME_NAME" \
        --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$MULTI_AGENT_IMAGE\"}}" \
        --role-arn "$MULTI_AGENT_ROLE_ARN" \
        --network-configuration '{"networkMode":"PUBLIC"}' \
        --authorizer-configuration "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_CLIENT_ID\"]}}" \
        --protocol-configuration '{"serverProtocol":"HTTP"}' \
        --region "$REGION" \
        --query 'agentRuntimeArn' --output text)
    echo "  Created runtime: $MA_RUNTIME_ARN"

    # Create endpoint
    aws bedrock-agentcore-control create-agent-runtime-endpoint \
        --agent-runtime-id "$(echo $MA_RUNTIME_ARN | awk -F/ '{print $NF}')" \
        --name "${MA_RUNTIME_NAME}-endpoint" \
        --region "$REGION" > /dev/null
    echo "  Created endpoint for Multi-Agent"
else
    echo "  Multi-Agent runtime already exists: $MA_RUNTIME_ARN"
fi

# Step E: Update runtime-config.json with AgentCore WebSocket URLs
echo "  [E] Updating runtime-config.json..."
RAG_WS_URL="wss://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/${RAG_RUNTIME_ARN}/ws"
MA_WS_URL="wss://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/${MA_RUNTIME_ARN}/ws"

# Get the UI bucket name
UI_BUCKET=$(jq -r ".[\"SRD-CloudFront-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"ui-url\")) | .value" cdk-outputs.json 2>/dev/null | head -1)
UI_BUCKET_NAME=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'srduibucket')].Name | [0]" --output text)

# Write updated runtime-config.json to S3
cat <<RCEOF | aws s3 cp - "s3://${UI_BUCKET_NAME}/runtime-config.json" --content-type application/json
{
  "cognitoUserPoolId": "$COGNITO_POOL_ID",
  "cognitoClientId": "$COGNITO_CLIENT_ID",
  "cognitoRegion": "$REGION",
  "ragWebSocketUrl": "$RAG_WS_URL",
  "multiAgentWebSocketUrl": "$MA_WS_URL"
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
echo "  RAG WebSocket:   $RAG_WS_URL"
echo "  Agent WebSocket: $MA_WS_URL"
echo ""
