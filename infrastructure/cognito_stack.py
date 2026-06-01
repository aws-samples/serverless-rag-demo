import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    aws_cognito as cognito,
    aws_iam as iam,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class CognitoStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        data_bucket_name: str,
        knowledge_base_id: str,
        data_source_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        # User Pool
        user_pool = cognito.UserPool(
            self, f"srd-user-pool-{env_name}",
            user_pool_name=env_params["rag-llm-user-pool"],
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # App Client
        user_pool_client = cognito.UserPoolClient(
            self, f"srd-user-pool-client-{env_name}",
            user_pool=user_pool,
            user_pool_client_name=f"srd-client-{env_name}",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            id_token_validity=Duration.days(1),
        )

        # Identity Pool — vends temporary AWS credentials to authenticated browser users
        identity_pool = cognito.CfnIdentityPool(
            self, f"srd-identity-pool-{env_name}",
            identity_pool_name=f"srd_identity_pool_{env_name}",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=user_pool_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name,
                )
            ],
        )

        # IAM role for Bedrock Evaluation service
        eval_service_role = iam.Role(
            self, f"srd-eval-service-role-{env_name}",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "EvalKBAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=[
                            f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                        ],
                    ),
                ]),
                "EvalS3Access": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/evaluations/*"],
                    ),
                ]),
            },
        )

        # IAM role for authenticated users — allows invoking AgentCore runtimes
        authenticated_role = iam.Role(
            self, f"srd-cognito-auth-role-{env_name}",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref,
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated",
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            inline_policies={
                "AgentCoreInvoke": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "bedrock-agentcore:InvokeAgentRuntime",
                            "bedrock-agentcore:InvokeAgentRuntimeWithWebSocketStream",
                        ],
                        resources=[
                            f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/*",
                        ],
                    ),
                ]),
                "S3DocumentAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="ListDocs",
                        actions=["s3:ListBucket"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}"],
                        conditions={"StringLike": {"s3:prefix": ["documents/*"]}},
                    ),
                    iam.PolicyStatement(
                        sid="ReadWriteDocs",
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/documents/*"],
                    ),
                ]),
                "KBSync": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:StartIngestionJob", "bedrock:ListIngestionJobs"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                ]),
                "BedrockEval": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "bedrock:CreateEvaluationJob",
                            "bedrock:GetEvaluationJob",
                            "bedrock:ListEvaluationJobs",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        sid="PassEvalRole",
                        actions=["iam:PassRole"],
                        resources=[eval_service_role.role_arn],
                        conditions={"StringEquals": {"iam:PassedToService": "bedrock.amazonaws.com"}},
                    ),
                ]),
                "S3EvalAndFeedback": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="EvalReadWrite",
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/evaluations/*"],
                    ),
                    iam.PolicyStatement(
                        sid="FeedbackWrite",
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/feedback/*"],
                    ),
                ]),
            },
        )

        # Attach role to identity pool
        cognito.CfnIdentityPoolRoleAttachment(
            self, f"srd-identity-pool-roles-{env_name}",
            identity_pool_id=identity_pool.ref,
            roles={"authenticated": authenticated_role.role_arn},
        )

        # Outputs
        self.user_pool_id = user_pool.user_pool_id
        self.client_id = user_pool_client.user_pool_client_id
        self.identity_pool_id = identity_pool.ref
        self.eval_role_arn = eval_service_role.role_arn

        CfnOutput(self, f"user-pool-id-{env_name}", value=user_pool.user_pool_id)
        CfnOutput(self, f"client-id-{env_name}", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, f"identity-pool-id-{env_name}", value=identity_pool.ref)
        CfnOutput(self, f"eval-role-arn-{env_name}",
                  value=eval_service_role.role_arn,
                  description="Bedrock Evaluation service role ARN")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG1", reason="Password policy configured above"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG2", reason="MFA not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG8", reason="Plus tier not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG7", reason="Identity pool uses authenticated role only"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5", reason="Wildcard on runtime/* allows invoking any runtime in this account"),
        ])
