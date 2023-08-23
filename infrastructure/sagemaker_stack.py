from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as _iam,
    aws_ecr as _ecr,
    aws_codebuild as _codebuild
)
from constructs import Construct
import os
import yaml


class SagemakerLLMStack(Stack):

     def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context('environment_name')
        config_details = self.node.try_get_context(env_name)
        # Create ECR Repo
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")
        build_spec_yml = ''
        with open("sagemakerspec.yml", "r") as stream:
            try:
                build_spec_yml = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        print(build_spec_yml)
        custom_sm_role = _iam.Role(self, f'llm_rag_role_{env_name}', 
                    role_name= config_details['sagemaker_role_name'],
                    assumed_by= _iam.CompositePrincipal(
                        _iam.ServicePrincipal('codebuild.amazonaws.com'),
                        _iam.ServicePrincipal('sagemaker.amazonaws.com')
                    )
        )
        sagemaker_policy = _iam.PolicyStatement(actions=["sagemaker:*", "s3:*", "iam:*"], resources=["*"])
        custom_sm_role.add_to_policy(sagemaker_policy)
        # Trigger CodeBuild job
        sagemaker_deploy_job =_codebuild.Project(
            self,
            f"sagemaker_deploy_{env_name}",
            build_spec=_codebuild.BuildSpec.from_object_to_yaml(build_spec_yml),
            role=custom_sm_role,
            environment = _codebuild.BuildEnvironment(
            build_image=_codebuild.LinuxBuildImage.STANDARD_6_0,
            privileged=True,
            environment_variables={
                "account_id" : _codebuild.BuildEnvironmentVariable(value = os.getenv("CDK_DEFAULT_ACCOUNT")),
                "region": _codebuild.BuildEnvironmentVariable(value = os.getenv("CDK_DEFAULT_REGION")),
                "sagemaker_endpoint": _codebuild.BuildEnvironmentVariable(value = config_details['sagemaker_endpoint'])
            })
        )

        
        
        
        
    
        
