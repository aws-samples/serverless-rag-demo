from aws_cdk import (
    NestedStack,
    aws_apprunner as _runner,
    aws_ecr as _ecr,
    Stack,
    aws_codebuild as _codebuild,
    aws_s3 as _s3,
    aws_s3_notifications as _s3_notifications,
    aws_lambda as _lambda,
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
        # Generate ECR Full repo name
        full_ecr_repo_name = f'{account_id}.dkr.ecr.{region}.amazonaws.com/{ecr_repo_name}:{current_timestamp}'
        
        apprunner_role = _iam.Role(self, f"rag-llm-role-{env_name}",
                  assumed_by=_iam.ServicePrincipal("build.apprunner.amazonaws.com"),
                )
        
        apprunner_role.add_to_policy(_iam.PolicyStatement(
                    actions=["ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability",
                            "ecr:BatchGetImage", "ecr:DescribeImages", "ecr:GetAuthorizationToken"],
                    resources=["*"],
                    effect=_iam.Effect.ALLOW
        ))
        
        
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
                                       port="80", 
                                       runtime_environment_variables=[_runner.CfnService.KeyValuePairProperty(
                                           name="name",
                                           value="value")],)))
                           )
        
        # Lets create an S3 bucket to store Images and also an API call
                    # create s3 bucket to store ocr related objects
        bucket_name = f'{config_details["s3_images_data"]}-{account_id}-{region}'
        cors_url='https://' + app_runner_ui.attr_service_url
        self.images_bucket = _s3.Bucket(self,
                                        id=config_details["s3_images_data"],
                                        bucket_name=bucket_name,
                                        auto_delete_objects=True,
                                        removal_policy=_cdk.RemovalPolicy.DESTROY,
                                        cors= [_s3.CorsRule(allowed_headers=["*"],
                                                            allowed_origins=[cors_url],
                                                            allowed_methods=[_s3.HttpMethods.GET, _s3.HttpMethods.POST],
                                                            id="serverless-rag-demo-cors-rule")],
                                        versioned=False)
        
        lambda_arn=f'arn:aws:lambda:{region}:{account_id}:function:{config_details["bedrock_indexing_function_name"]}'
        
        # Attach policy on bucket to invoke the lambda function
        self.images_bucket.add_to_resource_policy(
            _iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[lambda_arn],
                effect=_iam.Effect.ALLOW,
                principals=[_iam.ServicePrincipal("s3.amazonaws.com")]
        ))

        function = _lambda.Function.from_function_arn(self, f's3-notify-lambda-{env_name}', lambda_arn)
        # create s3 notification for lambda function
        notification = _s3_notifications.LambdaDestination(function)
        self.images_bucket.add_event_notification(_s3.EventType.OBJECT_CREATED, notification)
        self.images_bucket.add_event_notification(_s3.EventType.OBJECT_REMOVED_DELETE, notification)
        
        _cdk.CfnOutput(self, f"rag-llm-ecr-service-output-{env_name}", value=app_runner_ui.attr_service_url,
                       export_name="ServiceUrl"
                       )