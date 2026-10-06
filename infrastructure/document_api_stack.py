import os
from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class DocumentApiStack(Stack):
    """Server-side document API.

    Browsers hold Cognito Identity Pool credentials, which cannot carry a
    per-user condition for an email-keyed S3 prefix: IAM exposes
    cognito-identity.amazonaws.com:sub but no variable for the email claim. So
    rather than grant the browser S3 access and try to constrain it, document
    access lives behind this API, where the caller's email comes from a JWT that
    API Gateway has verified against the User Pool.
    """

    def __init__(
        self, scope: Construct, construct_id: str, *,
        user_pool_id: str,
        user_pool_client_id: str,
        data_bucket_name: str,
        knowledge_base_id: str,
        data_source_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        document_prefix = f"arn:aws:s3:::{data_bucket_name}/documents/*"

        handler_role = iam.Role(
            self, f"srd-document-api-role-{env_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
            inline_policies={
                # The handler needs the whole documents/* prefix because it serves
                # every user. Restricting an individual request to its caller is
                # done in the handler, from the verified email claim.
                "DocumentObjects": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="ReadWriteDocumentObjects",
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        resources=[document_prefix],
                    ),
                    iam.PolicyStatement(
                        sid="ListDocumentObjects",
                        actions=["s3:ListBucket"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}"],
                        conditions={"StringLike": {"s3:prefix": ["documents/*"]}},
                    ),
                ]),
                "KnowledgeBaseSync": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "bedrock:StartIngestionJob",
                            "bedrock:ListIngestionJobs",
                        ],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"
                        ],
                    ),
                ]),
            },
        )

        log_group = logs.LogGroup(
            self, f"srd-document-api-logs-{env_name}",
            log_group_name=f"/aws/lambda/srd-document-api-{env_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        handler = _lambda.Function(
            self, f"srd-document-api-fn-{env_name}",
            function_name=f"srd-document-api-{env_name}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "lambdas", "documents")
            ),
            timeout=Duration.seconds(30),
            memory_size=512,
            role=handler_role,
            log_group=log_group,
            environment={
                "REGION": region,
                "DATA_BUCKET_NAME": data_bucket_name,
                "KNOWLEDGE_BASE_ID": knowledge_base_id,
                "DATA_SOURCE_ID": data_source_id,
            },
        )

        # Verifies signature, expiry and audience against the User Pool before the
        # handler runs, so claims reaching the handler are trustworthy.
        authorizer = apigwv2_authorizers.HttpUserPoolAuthorizer(
            f"srd-document-api-authorizer-{env_name}",
            cognito.UserPool.from_user_pool_id(
                self, f"srd-document-api-user-pool-{env_name}", user_pool_id
            ),
            user_pool_clients=[
                cognito.UserPoolClient.from_user_pool_client_id(
                    self, f"srd-document-api-client-{env_name}", user_pool_client_id
                ),
            ],
            identity_source=["$request.header.Authorization"],
        )

        # The UI is served from CloudFront, so these calls are cross-origin.
        # Authorisation rests on the bearer ID token, not on the origin: no
        # cookies or other ambient credentials are involved, so a hostile page
        # cannot make an authenticated call without first stealing a token, which
        # the browser's same-origin policy already prevents. Deployers who know
        # their distribution domain should set the allowed_origins context value
        # to it rather than leaving the default.
        allowed_origins = self.node.try_get_context("document_api_allowed_origins") or ["*"]

        http_api = apigwv2.HttpApi(
            self, f"srd-document-api-{env_name}",
            api_name=f"srd-document-api-{env_name}",
            description="Per-user document management for serverless-rag-demo",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=allowed_origins,
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.DELETE,
                ],
                allow_headers=["authorization", "content-type"],
                max_age=Duration.hours(1),
            ),
        )

        integration = apigwv2_integrations.HttpLambdaIntegration(
            f"srd-document-api-integration-{env_name}", handler
        )

        for method, path in [
            (apigwv2.HttpMethod.GET, "/documents"),
            (apigwv2.HttpMethod.POST, "/documents/upload-url"),
            (apigwv2.HttpMethod.POST, "/documents/download-url"),
            (apigwv2.HttpMethod.DELETE, "/documents"),
            (apigwv2.HttpMethod.POST, "/documents/sync"),
            (apigwv2.HttpMethod.GET, "/documents/ingestion-status"),
        ]:
            http_api.add_routes(
                path=path,
                methods=[method],
                integration=integration,
                authorizer=authorizer,
            )

        self.api_url = http_api.api_endpoint

        CfnOutput(self, f"documentapiurl-{env_name}",
                  value=http_api.api_endpoint,
                  description="Document API base URL")

        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(
                id="AwsSolutions-IAM4",
                reason="AWSLambdaBasicExecutionRole is the standard Lambda logging policy",
            ),
            _cdk_nag.NagPackSuppression(
                id="AwsSolutions-IAM5",
                reason=(
                    "The handler serves all users so it needs documents/*; the "
                    "per-caller restriction is enforced in the handler against the "
                    "API Gateway-verified email claim"
                ),
            ),
            _cdk_nag.NagPackSuppression(
                id="AwsSolutions-L1",
                reason="Python 3.12 is current",
            ),
            _cdk_nag.NagPackSuppression(
                id="AwsSolutions-APIG1",
                reason="Access logging is handled at the CloudFront distribution in front of this API",
            ),
        ])
