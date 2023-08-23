from aws_cdk import (
    NestedStack,
    aws_lambda as _lambda,
    aws_iam as _iam,
    aws_ecr as _ecr,
    aws_codebuild as _codebuild,
    aws_stepfunctions_tasks as _tasks,
    aws_stepfunctions as _sfn
)
from constructs import Construct
import os
import yaml


class Ecr_stack(NestedStack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context('environment_name')
        config_details = self.node.try_get_context(env_name)
        ecr_repo_name = config_details['ecr_repository_name']
        # Create ECR Repo
        _ecr.Repository(self, ecr_repo_name, repository_name=ecr_repo_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")
        current_timestamp = self.node.try_get_context('current_timestamp')
        # Generate ECR Full repo name
        full_ecr_repo_name = f'{account_id}.dkr.ecr.{region}.amazonaws.com/{ecr_repo_name}:{current_timestamp}'
    
        build_spec_yml = ''
        with open("buildspec.yml", "r") as stream:
            try:
                build_spec_yml = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        print(build_spec_yml)

        # Trigger CodeBuild job
        containerize_build_job =_codebuild.Project(
            self,
            f"lambda_rag_llm_container_{env_name}",
            build_spec=_codebuild.BuildSpec.from_object_to_yaml(build_spec_yml),
            environment = _codebuild.BuildEnvironment(
            build_image=_codebuild.LinuxBuildImage.STANDARD_6_0,
            privileged=True,
            environment_variables={
                "ecr_repo": _codebuild.BuildEnvironmentVariable(value = full_ecr_repo_name),
                "account_id" : _codebuild.BuildEnvironmentVariable(value = os.getenv("CDK_DEFAULT_ACCOUNT")),
                "region": _codebuild.BuildEnvironmentVariable(value = os.getenv("CDK_DEFAULT_REGION"))
            })
        )

        ecr_policy = _iam.PolicyStatement(actions=[
        "ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:GetAuthorizationToken",
        "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart", "ecr:CreateRepository"
        ], resources=["*"])
        containerize_build_job.add_to_role_policy(ecr_policy)
        
        
        

        
        
