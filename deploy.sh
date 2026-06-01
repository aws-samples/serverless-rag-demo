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

echo ""
echo "  Deploying..."

# Bootstrap CDK if needed
cdk bootstrap "aws://$CDK_DEFAULT_ACCOUNT/$REGION" 2>/dev/null || true

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
    UI_URL=$(jq -r '.. | objects | to_entries[] | select(.key | contains("ui-url")) | .value' cdk-outputs.json 2>/dev/null | head -1)
    if [[ -n "$UI_URL" ]]; then
        echo "  UI: $UI_URL"
    fi
fi

echo ""
