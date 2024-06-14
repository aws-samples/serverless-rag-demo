from aws_cdk import (
    NestedStack,
    aws_apprunner as _runner,
    aws_ecr as _ecr,
    Stack,
    aws_codebuild as _codebuild,
    aws_iam as _iam)

from constructs import Construct
import os
import yaml
import aws_cdk as _cdk

# This stack will dockerize the latest UI build and upload it to ECR
class AppRunnerHostingStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())
        env_name = self.node.try_get_context('environment_name')
        config_details = self.node.try_get_context(env_name)
        
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")
        current_timestamp = self.node.try_get_context('current_timestamp')
        
        ecr_repo_name = config_details['ecr_repository_name']
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")
        current_timestamp = self.node.try_get_context('current_timestamp')
        # Generate ECR Full repo name
        full_ecr_repo_name = f'{account_id}.dkr.ecr.{region}.amazonaws.com/{ecr_repo_name}:{current_timestamp}'
        
        apprunner_policy_document = _iam.PolicyDocument(
            assign_sids=True,
            statements=[
                _iam.PolicyStatement(
                    actions=["ecr:GetAuthorizationToken"],
                    resources=["*"],
                    effect=_iam.Effect.ALLOW
                ),
                _iam.PolicyStatement(
                    actions=["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
                            "ecr:GetRepositoryPolicy","ecr:DescribeRepositories", "ecr:ListImages",
                            "ecr:DescribeImages","ecr:BatchGetImage","ecr:GetLifecyclePolicy",
                            "ecr:GetLifecyclePolicyPreview","ecr:ListTagsForResource",
                            "ecr:DescribeImageScanFindings"],
                    resources=["arn:aws:ecr:" + region + ":" + account_id + "repository/" + ecr_repo_name],
                    effect=_iam.Effect.ALLOW
                )
            ]
        )

        apprunner_role = _iam.Role(self, f"rag-llm-role-{env_name}",
                  assumed_by=_iam.ServicePrincipal("build.apprunner.amazonaws.com"),
                  inline_policies={"AppRunnerPolicy": apprunner_policy_document}
                )

        app_runner_ui = _runner.CfnService(self, f"rag-llm-ecr-service-{env_name}",
                            instance_configuration=_runner.CfnService.InstanceConfigurationProperty(
                            cpu="2048",
                            memory="4096"
                            ),
                            service_name=config_details['apprunner_service_name'],
                            source_configuration=_runner.CfnService.SourceConfigurationProperty(
                                auto_deployments_enabled=True,
                                authentication_configuration=_runner.CfnService.AuthenticationConfigurationProperty(
                                    access_role_arn=apprunner_role.role_arn
                                ),
                                image_repository=_runner.CfnService.ImageRepositoryProperty(
                                   image_identifier=full_ecr_repo_name,
                                   image_repository_type="ECR",
                                   image_configuration=_runner.CfnService.ImageConfigurationProperty(
                                       port="3001", 
                                       runtime_environment_variables=[_runner.CfnService.KeyValuePairProperty(
                                           name="name",
                                           value="value")],)))
                           )
        
        _cdk.CfnOutput(self, f"rag-llm-ecr-service-output-{env_name}", value=app_runner_ui.attr_service_url,
                       export_name="ServiceUrl"
                       )