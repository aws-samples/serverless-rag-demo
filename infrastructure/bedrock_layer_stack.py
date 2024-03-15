from aws_cdk import (
    NestedStack,
    aws_lambda as _lambda,
    aws_iam as _iam,
    aws_codebuild as _codebuild,
    aws_kms as _kms,
    Aspects
)
from constructs import Construct
import os
import yaml
import cdk_nag as _cdk_nag
import aws_cdk as _cdk

# This stack creates the bedrock lambda layers needed for indexing/querying models in Bedrock
class BedrockLayerStack(NestedStack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())
        env_name = self.node.try_get_context('environment_name')
        config_details = self.node.try_get_context(env_name)
        boto3_bedrock_layer_name = config_details['boto3_bedrock_layer']
        opensearchpy_layer_name = config_details['opensearchpy_layer']
        langchainpy_layer_name = config_details['langchainpy_layer_name']
        aws4auth_layer_name = config_details['aws4auth_layer']
        
        llm_model_id = 'random'
        try:
            llm_model_id = self.node.get_context("llm_model_id")
        except Exception as e:
            pass

        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")
        current_timestamp = self.node.try_get_context('current_timestamp')
        
        build_spec_yml = ''
        with open("buildspec_bedrock.yml", "r") as stream:
            try:
                build_spec_yml = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        
        
        # Trigger CodeBuild job
        containerize_build_job =_codebuild.Project(
            self,
            f"lambda_rag_llm_container_{env_name}",
            build_spec=_codebuild.BuildSpec.from_object_to_yaml(build_spec_yml),
            environment = _codebuild.BuildEnvironment(
            build_image=_codebuild.LinuxBuildImage.STANDARD_6_0,
            privileged=True,
            environment_variables={
                "boto3_bedrock_layer_name": _codebuild.BuildEnvironmentVariable(value = boto3_bedrock_layer_name),
                "opensearchpy_layer_name": _codebuild.BuildEnvironmentVariable(value = opensearchpy_layer_name),
                "aws4auth_layer_name": _codebuild.BuildEnvironmentVariable(value = aws4auth_layer_name),
                "langchainpy_layer_name":  _codebuild.BuildEnvironmentVariable(value = langchainpy_layer_name),
                "account_id" : _codebuild.BuildEnvironmentVariable(value = account_id),
                "region": _codebuild.BuildEnvironmentVariable(value = region)
            })
        )

        lambda_layer_policy = _iam.PolicyStatement(actions=[
        "lambda:PublishLayerVersion"
        ], resources=["*"])
        containerize_build_job.add_to_role_policy(lambda_layer_policy)
        self.suppressor([containerize_build_job], 'AwsSolutions-IAM5', 'We cannot remove wildcard here, as the CodeBuild should have permissions to publish different layer versions')

        
    def suppressor(self, constructs, id, reason):
        if len(reason) < 10:
            reason = reason + ' Will work on this at a later date.'
        _cdk_nag.NagSuppressions.add_resource_suppressions(constructs, [
            _cdk_nag.NagPackSuppression(id=id, reason=reason)
        ], apply_to_children=True)
            
        

        
        
