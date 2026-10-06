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


class AppApiStack(Stack):
    """Server-side API for everything that needs per-user authorisation.

    Browsers hold Cognito Identity Pool credentials, and those cannot express
    "only this user's data" for the resources this app keeps per user:

      * documents and evaluation output are keyed by email, and IAM exposes
        cognito-identity.amazonaws.com:sub but no variable for the email claim
      * bedrock:CreateEvaluationJob and bedrock:ListEvaluationJobs have no
        resource-level support at all, so they can only be granted on "*"

    Granting any of that to the browser means granting it for every user. So the
    permissions sit on this Lambda role, which no user controls, and the handler
    decides what each request may touch using the email claim API Gateway has
    already verified against the User Pool.
    """

    def __init__(
        self, scope: Construct, construct_id: str, *,
        user_pool_id: str,
        user_pool_client_id: str,
        data_bucket_name: str,
        knowledge_base_id: str,
        data_source_id: str,
        eval_role_arn: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        bucket_arn = f"arn:aws:s3:::{data_bucket_name}"

        handler_role = iam.Role(
            self, f"srd-app-api-role-{env_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
            inline_policies={
                # The handler serves every user, so it needs the whole prefix.
                # Restricting an individual request to its caller is done in the
                # handler, from the verified email claim.
                "DataObjects": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="ReadWriteDocuments",
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        resources=[f"{bucket_arn}/documents/*"],
                    ),
                    iam.PolicyStatement(
                        sid="ReadWriteEvaluations",
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"{bucket_arn}/evaluations/*"],
                    ),
                    iam.PolicyStatement(
                        sid="WriteFeedback",
                        actions=["s3:PutObject"],
                        resources=[f"{bucket_arn}/feedback/*"],
                    ),
                    iam.PolicyStatement(
                        sid="ListDataObjects",
                        actions=["s3:ListBucket"],
                        resources=[bucket_arn],
                        conditions={
                            "StringLike": {
                                "s3:prefix": ["documents/*", "evaluations/*"],
                            },
                        },
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
                "Evaluations": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="ReadOwnEvaluationJob",
                        actions=["bedrock:GetEvaluationJob"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:evaluation-job/*"
                        ],
                    ),
                    iam.PolicyStatement(
                        # Neither action supports resource-level permissions, so
                        # "*" is the only form IAM accepts. The handler names
                        # every job with an opaque per-user tag and filters on it,
                        # so a caller still only ever sees its own jobs.
                        sid="CreateAndListEvaluationJobs",
                        actions=[
                            "bedrock:CreateEvaluationJob",
                            "bedrock:ListEvaluationJobs",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        sid="PassEvalRole",
                        actions=["iam:PassRole"],
                        resources=[eval_role_arn],
                        conditions={
                            "StringEquals": {
                                "iam:PassedToService": "bedrock.amazonaws.com",
                            },
                        },
                    ),
                ]),
            },
        )

        log_group = logs.LogGroup(
            self, f"srd-app-api-logs-{env_name}",
            log_group_name=f"/aws/lambda/srd-app-api-{env_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        handler = _lambda.Function(
            self, f"srd-app-api-fn-{env_name}",
            function_name=f"srd-app-api-{env_name}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "lambdas", "api")
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
                "EVAL_ROLE_ARN": eval_role_arn,
                "EVALUATOR_MODEL_ARN": (
                    f"arn:aws:bedrock:{region}::foundation-model/amazon.nova-pro-v1:0"
                ),
                "GENERATOR_MODEL_ARN": "global.anthropic.claude-sonnet-4-6",
            },
        )

        # Verifies signature, expiry and audience against the User Pool before the
        # handler runs, so claims reaching the handler are trustworthy.
        authorizer = apigwv2_authorizers.HttpUserPoolAuthorizer(
            f"srd-app-api-authorizer-{env_name}",
            cognito.UserPool.from_user_pool_id(
                self, f"srd-app-api-user-pool-{env_name}", user_pool_id
            ),
            user_pool_clients=[
                cognito.UserPoolClient.from_user_pool_client_id(
                    self, f"srd-app-api-client-{env_name}", user_pool_client_id
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
        allowed_origins = self.node.try_get_context("app_api_allowed_origins") or ["*"]

        http_api = apigwv2.HttpApi(
            self, f"srd-app-api-{env_name}",
            api_name=f"srd-app-api-{env_name}",
            description="Authenticated per-user API for serverless-rag-demo",
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
            f"srd-app-api-integration-{env_name}", handler
        )

        for method, path in [
            (apigwv2.HttpMethod.GET, "/documents"),
            (apigwv2.HttpMethod.POST, "/documents/upload-url"),
            (apigwv2.HttpMethod.POST, "/documents/download-url"),
            (apigwv2.HttpMethod.DELETE, "/documents"),
            (apigwv2.HttpMethod.POST, "/documents/sync"),
            (apigwv2.HttpMethod.GET, "/documents/ingestion-status"),
            (apigwv2.HttpMethod.POST, "/evaluations"),
            (apigwv2.HttpMethod.GET, "/evaluations"),
            (apigwv2.HttpMethod.GET, "/evaluations/status"),
            (apigwv2.HttpMethod.GET, "/evaluations/results"),
            (apigwv2.HttpMethod.POST, "/feedback"),
        ]:
            http_api.add_routes(
                path=path,
                methods=[method],
                integration=integration,
                authorizer=authorizer,
            )

        self.api_url = http_api.api_endpoint

        CfnOutput(self, f"appapiurl-{env_name}",
                  value=http_api.api_endpoint,
                  description="Authenticated app API base URL")

        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(
                id="AwsSolutions-IAM4",
                reason="AWSLambdaBasicExecutionRole is the standard Lambda logging policy",
            ),
            _cdk_nag.NagPackSuppression(
                id="AwsSolutions-IAM5",
                reason=(
                    "The handler serves all users so it needs the documents/, "
                    "evaluations/ and feedback/ prefixes, and the Bedrock evaluation "
                    "create/list actions accept no resource. Per-caller restriction "
                    "is enforced in the handler against the API Gateway-verified "
                    "email claim"
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
