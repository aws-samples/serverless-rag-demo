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

deployment_region=$(curl -s http://169.254.169.254/task/AvailabilityZone | sed 's/\(.*\)[a-z]/\1/')
embed_model_id='amazon.titan-embed-text-v2:0'
if [ -z "$deployment_region" ]
then
    printf  "$Red !!! Cannot detect region. Manually select your AWS Cloudshell region from the below list $NC"
    printf "\n"
    printf "$Green Please enter your current AWS cloudshell region (1/2/3/4/5/6): $NC"
    printf "\n"
    region_options=("us-east-1" "us-west-2" "ap-southeast-1" "ap-northeast-1" "ap-south-1" "eu-central-1" "Quit")
    select region_opts in "${region_options[@]}"
    do
        case $region_opts in 
            "us-east-1")
                deployment_region='us-east-1'
                printf "$Green Deploy in US East(N.Virginia) $NC"
                printf "\n"
                ;; 
            "us-west-2")
                deployment_region='us-west-2'
                printf "$Green Deploy in US West(Oregon) $NC"
                ;;
            "ap-southeast-1")
                deployment_region='ap-southeast-1'
                printf "$Green Deploy in Asia Pacific (Singapore) $NC"
                ;;
            "ap-northeast-1")
                deployment_region='ap-northeast-1'
                printf "$Green Deploy in Asia Pacific (Tokyo) $NC"
                ;;
            "ap-south-1")
                deployment_region='ap-south-1'
                printf "$Green Deploy in Asia Pacific (Mumbai) $NC"
                ;;
            "eu-central-1")
                deployment_region='eu-central-1'
                printf "$Green Deploy in Europe (Frankfurt) $NC"
                ;;
            "Quit")
                printf "$Red Quit deployment $NC"
                exit 1
                break
                ;;
            *)
            printf "$Red Exiting, Invalid option $REPLY. Select from 1/2/3/4/5/6 $NC"
            exit 1;;
        esac
        break
    done
fi
echo "Selected region: $deployment_region "

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
sudo npm install -g aws-cdk@2.91.0

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
