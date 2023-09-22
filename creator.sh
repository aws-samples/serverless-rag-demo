#!/usr/bin/bash 
echo "environment: $1"
if [ -z "$1" ]
then
    echo "Pass the environment as dev, qa or sandbox"
    exit 1
fi
if [ $1 != "dev" -a $1 != "qa" -a $1 != "sandbox" ]
then
    echo "Environment name can only be dev or qa or sandbox. example 'sh creator.sh dev' "
    exit 1
fi

if [ -z "$2" ]
then
    echo "Region not passed. Defaulting to us-east-1"
    deployment_region='us-east-1'
else
    deployment_region=$2
fi
PS3='Please enter your LLM choice (1/2/3/4/5/6): '
options=("Llama2-7B" "Llama2-13B" "Llama2-70B" "Falcon-7B" "Falcon-40B" "Falcon-180B" "Quit")
model_id='meta-textgeneration-llama-2-7b-f'
instance_type='ml.g5.2xlarge'
select opt in "${options[@]}"
do
    case $opt in
        "Llama2-7B")
            instance_type='ml.g5.2xlarge'
            model_id='meta-textgeneration-llama-2-7b-f'
            ;;
        "Llama2-13B")
            instance_type='ml.g5.12xlarge'
            model_id='meta-textgeneration-llama-2-13b-f'
            ;;
        "Llama2-70B")
            instance_type='ml.g5.48xlarge'
            model_id='meta-textgeneration-llama-2-70b-f'
            ;;
        "Falcon-7B")
            instance_type='ml.g5.2xlarge'
            model_id='huggingface-llm-falcon-7b-bf16'
            ;;
        "Falcon-40B")
            instance_type='ml.g5.12xlarge'
            model_id='huggingface-llm-falcon-40b-bf16'
            ;;
        "Falcon-180B")
            instance_type='ml.p4de.24xlarge'
            model_id='huggingface-llm-falcon-180b-bf16'
            ;;
        "Quit")
            break
            ;;
        *) echo "invalid option $REPLY";;
    esac
    break
done

echo '*************************************************************'
echo ' '
echo  !!! Attention The $opt model will be deployed on $instance_type . Check Service Quotas to apply for limit increase
echo ' '
echo '*************************************************************'
echo ' '
echo ' '
read -p "Press Enter to proceed with deployment else ctrl+c to cancel"

cd ..
echo "--- Upgrading npm ---"
sudo npm install n stable -g
echo "--- Installing cdk ---"
sudo npm install -g aws-cdk@2.91.0

echo "--- Bootstrapping CDK on account in region $deployment_region ---"
cdk bootstrap aws://$(aws sts get-caller-identity --query "Account" --output text)/$deployment_region

cd serverless-rag-demo
echo "--- pip install requirements ---"
python3 -m pip install -r requirements.txt

echo "--- CDK synthesize ---"
cdk synth -c environment_name=$1 -c current_timestamp=$CURRENT_UTC_TIMESTAMP

echo "--- CDK deploy ---"
CURRENT_UTC_TIMESTAMP=$(date -u +"%Y%m%d%H%M%S")
echo Setting Tagging Lambda Image with timestamp $CURRENT_UTC_TIMESTAMP
cdk deploy -c environment_name=$1 -c current_timestamp=$CURRENT_UTC_TIMESTAMP LlmsWithServerlessRagStack --require-approval never
echo "--- Get Build Container ---"
project=lambdaragllmcontainer"$1"
echo project: $project
build_container=$(aws codebuild list-projects|grep -o $project'[^,"]*')
echo container: $build_container
echo "--- Trigger Build ---"
BUILD_ID=$(aws codebuild start-build --project-name $build_container | jq '.build.id' -r)
echo Build ID : $BUILD_ID
if [ "$?" != "0" ]; then
    echo "Could not start CodeBuild project. Exiting."
    exit 1
else
    echo "Build started successfully."
fi

echo "Check build status every 30 seconds. Wait for codebuild to finish"
j=0
while [ $j -lt 50 ];
do 
    sleep 30
    echo 'Wait for 30 seconds. Build job typically takes 15 minutes to complete...'
    build_status=$(aws codebuild batch-get-builds --ids $BUILD_ID | jq -cs '.[0]["builds"][0]["buildStatus"]')
    build_status="${build_status%\"}"
    build_status="${build_status#\"}"
    if [ $build_status = "SUCCEEDED" ] || [ $build_status = "FAILED" ] || [ $build_status = "STOPPED" ]
    then
        echo "Build complete: $latest_build : status $build_status"
        break
    fi
    ((j++))
done

if [ $build_status = "SUCCEEDED" ]
then
    COLLECTION_NAME=$(jq '.context.'$1'.collection_name' cdk.json -r)
    COLLECTION_ENDPOINT=$(aws opensearchserverless batch-get-collection --names $COLLECTION_NAME |jq '.collectionDetails[0]["collectionEndpoint"]' -r)
    cdk deploy -c environment_name=$1 -c collection_endpoint=$COLLECTION_ENDPOINT -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c llm_model_id=$model_id ApiGwLlmsLambda"$1"Stack --require-approval never
    cdk deploy -c environment_name=$1 -c llm_model_id=$model_id SagemakerLlmdevStack --require-approval never
    echo "--- Get Sagemaker Deployment Container ---"
    project=sagemakerdeploy"$1"
    build_container=$(aws codebuild list-projects|grep -o $project'[^,"]*')
    echo container: $build_container
    echo "--- Trigger Build ---"
    BUILD_ID=$(aws codebuild start-build --project-name $build_container | jq '.build.id' -r)
    echo Build ID : $BUILD_ID
    if [ "$?" != "0" ]; then
        echo "Could not start Sagemaker CodeBuild project. Exiting."
        exit 1
    else
        echo "Build started successfully."
        echo "Check Sagemaker Model deployment status every 30 seconds. Wait for codebuild to finish."
        j=0
        while [ $j -lt 500 ];
        do 
            sleep 30
            echo 'Wait for 30 seconds. Build job typically takes 20 minutes to complete...'
            build_status=$(aws codebuild batch-get-builds --ids $BUILD_ID | jq -cs '.[0]["builds"][0]["buildStatus"]')
            build_status="${build_status%\"}"
            build_status="${build_status#\"}"
            if [ $build_status = "SUCCEEDED" ] || [ $build_status = "FAILED" ] || [ $build_status = "STOPPED" ]
            then
                echo "Sagemaker deployment complete: $latest_build : status $build_status"
                break
            fi
            ((j++))
        done
    fi
else
    echo "Exiting. Build did not succeed."
fi

echo "Deployment Complete"
