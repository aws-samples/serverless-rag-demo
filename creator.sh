#!/usr/bin/bash 
Green='\033[0;32m'
Red='\033[0;31m'
NC='\033[0m'

if [ -z "$1" ]
then
    infra_env='dev'
else
    infra_env=$1
fi  

if [ $infra_env != "dev" -a $infra_env != "qa" -a $infra_env != "sandbox" ]
then
    echo "Environment name can only be dev or qa or sandbox. example 'sh creator.sh dev' "
    exit 1
fi
echo "Environment: $infra_env"

deployment_region=$(aws ec2 describe-availability-zones --output text --query 'AvailabilityZones[0].RegionName')
embed_model_id='cohere.embed-english-v3'

printf "$Green Selected region: $deployment_region $NC \n"
printf "$Green Selected embedding model: $embed_model_id $NC \n"

echo '*************************************************************'
echo ' '

echo '*************************************************************'
echo ' '

printf "$Green Do you want to deploy Opensearch Serverless or Just try out Amazon Bedrock: $NC"
printf "\n"
options=("Yes - Deploy Amazon Opensearch Serverless vector engine for RAG" "No - I will only test Amazon Bedrock without RAG" "Quit")
aoss_selected='yes'
select opt in "${options[@]}"
do
    case $opt in
        "Yes - Deploy Amazon Opensearch Serverless vector engine for RAG")
            aoss_selected='yes'
            ;;
        "No - I will only test Amazon Bedrock without RAG")
            aoss_selected='no'
            printf "$Green You can re-run this script to deploy Opensearch Serverless later $NC"
            ;;
        "Quit")
            printf "$Red Quit deployment $NC"
            exit 1
            break
            ;;
        *)
        printf "$Red Exiting, Invalid option $REPLY . Select from 1/2/3 $NC"
        exit 1
        ;;
    esac
    break
done

echo ' '
echo '*************************************************************'
echo ' '
printf "$Green Press Enter to proceed with deployment else ctrl+c to cancel $NC "
read -p " "

cd ..
echo "--- Upgrading npm ---"
sudo npm install n stable -g
echo "--- Installing cdk ---"
sudo npm install -g aws-cdk@2.1016.1

echo "--- Bootstrapping CDK on account in region $deployment_region ---"
cdk bootstrap aws://$(aws sts get-caller-identity --query "Account" --output text)/$deployment_region

cd serverless-rag-demo
echo "--- pip install requirements ---"
python3 -m pip install -r requirements.txt

echo "--- CDK synthesize ---"
cdk synth -c environment_name=$infra_env -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c is_aoss=$aoss_selected -c embed_model_id=$embed_model_id

echo "--- CDK deploy ---"
CURRENT_UTC_TIMESTAMP=$(date -u +"%Y%m%d%H%M%S")
echo Setting Tagging Lambda Image with timestamp $CURRENT_UTC_TIMESTAMP
cdk deploy -c environment_name=$infra_env -c current_timestamp=$CURRENT_UTC_TIMESTAMP  -c is_aoss="$aoss_selected" -c embed_model_id=$embed_model_id LlmsWithServerlessRag"$infra_env"Stack --require-approval never

# Create an S3 bucket only if it doesn't exist to store lambda layer artifacts
# get the aws account id
account_id=$(aws sts get-caller-identity --query "Account" --output text)
s3_bucket_name=serverless-rag-demo-$infra_env-$account_id-$deployment_region
if ! aws s3 ls "s3://$s3_bucket_name" 2>&1 > /dev/null; then
    echo "S3 bucket $s3_bucket_name does not exist. Creating it..."
    aws s3 mb s3://$s3_bucket_name
else
    echo "S3 bucket $s3_bucket_name already exists."
fi

echo "--- Get Build Container ---"
project=lambdaragllmcontainer"$infra_env"
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
    COLLECTION_ENDPOINT=https://dummy-vector-endpoint.amazonaws.com
    if [ $aoss_selected = "yes" ]
    then
        COLLECTION_NAME=$(jq '.context.'$infra_env'.collection_name' cdk.json -r)
        COLLECTION_ENDPOINT=$(aws opensearchserverless batch-get-collection --names $COLLECTION_NAME |jq '.collectionDetails[0]["collectionEndpoint"]' -r)
    fi

    cdk deploy -c environment_name=$infra_env -c collection_endpoint=$COLLECTION_ENDPOINT -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c is_aoss=$aoss_selected -c embed_model_id=$embed_model_id ApiGwLlmsLambda"$infra_env"Stack --require-approval never
    
    echo "---Deploying the UI ---"
    project=ragllmuicontainer"$infra_env"
    echo project: $project
    build_container=$(aws codebuild list-projects|grep -o $project'[^,"]*')
    echo container: $build_container
    echo "--- Trigger UI Build ---"
    BUILD_ID=$(aws codebuild start-build --project-name $build_container | jq '.build.id' -r)
    echo Build ID : $BUILD_ID
    if [ "$?" != "0" ]; then
        echo "Could not start UI CodeBuild project. Exiting."
        exit 1
    else
        echo "UI Build started successfully."
    fi

    echo "Check UI build status every 30 seconds. Wait for codebuild to finish"
    j=0
    while [ $j -lt 50 ];
    do 
        sleep 10
        echo 'Wait for 30 seconds. Build job typically takes 5 minutes to complete...'
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
       echo "Host UI on AppRunner..."
       cdk deploy -c environment_name=$infra_env -c collection_endpoint=$COLLECTION_ENDPOINT -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c is_aoss=$aoss_selected -c embed_model_id=$embed_model_id AppRunnerHosting"$infra_env"Stack --require-approval never
    else
       echo "Exiting. Build did not succeed."
       exit 1
    fi

else
    echo "Exiting. Build did not succeed."
    exit 1
fi

echo "Deployment Complete"
