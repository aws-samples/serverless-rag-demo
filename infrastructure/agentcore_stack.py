import os
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class AgentCoreStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        knowledge_base_id: str,
        data_bucket_name: str,
        collection_endpoint: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        model_id = env_params["default_llm_model"]

        # Build container images
        multi_agent_image = ecr_assets.DockerImageAsset(
            self, f"srd-multi-agent-image-{env_name}",
            directory=os.path.join(os.getcwd(), "containers/multi-agent"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        rag_query_image = ecr_assets.DockerImageAsset(
            self, f"srd-rag-query-image-{env_name}",
            directory=os.path.join(os.getcwd(), "containers/rag-query"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # ECR pull permissions (required by AgentCore to pull container images)
        ecr_pull_statement = iam.PolicyStatement(
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer",
            ],
            resources=["*"],
        )

        # IAM role for Multi-Agent runtime
        multi_agent_role = iam.Role(
            self, f"srd-multi-agent-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            ),
            inline_policies={
                "MultiAgentPolicy": iam.PolicyDocument(statements=[
                    ecr_pull_statement,
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                            f"arn:aws:bedrock:*::foundation-model/amazon.nova-*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                    iam.PolicyStatement(
                        sid="GeneratedArtefacts",
                        # The runtime writes generated decks and HTML, then
                        # presigns them for download — a presigned URL carries
                        # the signer's permissions, so GetObject is needed here
                        # too. Both are confined to the two prefixes it owns:
                        # users' documents live under documents/ and must stay
                        # out of reach of an agent the model is driving.
                        actions=["s3:PutObject", "s3:GetObject"],
                        resources=[
                            f"arn:aws:s3:::{data_bucket_name}/generated-code/*",
                            f"arn:aws:s3:::{data_bucket_name}/generated-ppt/*",
                        ],
                    ),
                    iam.PolicyStatement(
                        sid="InvokeWebSearchGateway",
                        actions=["bedrock-agentcore:InvokeGateway"],
                        resources=[
                            f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*"
                        ],
                    ),
                ]),
            },
        )

        # Service role the Web Search Gateway assumes. The Gateway is created by
        # deploy.sh rather than CDK because connector targets need a newer
        # bedrock-agentcore-control model than the pinned CDK/CLI carries, so the
        # role is created here and its ARN handed over.
        gateway_role = iam.Role(
            self, f"srd-gateway-role-{env_name}",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn":
                            f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*"
                    },
                },
            ),
            inline_policies={
                "WebSearchGatewayPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="InvokeGateway",
                        actions=["bedrock-agentcore:InvokeGateway"],
                        resources=[
                            f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*"
                        ],
                    ),
                    iam.PolicyStatement(
                        sid="InvokeWebSearch",
                        # A service-owned ARN, checked per request. It is the
                        # only outbound destination the agent can now reach:
                        # there is no URL for the model to choose.
                        actions=["bedrock-agentcore:InvokeWebSearch"],
                        resources=[
                            f"arn:aws:bedrock-agentcore:{region}:aws:tool/web-search.v1"
                        ],
                    ),
                ]),
            },
        )

        # IAM role for RAG Query runtime
        rag_query_role = iam.Role(
            self, f"srd-rag-query-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            ),
            inline_policies={
                "RAGQueryPolicy": iam.PolicyDocument(statements=[
                    ecr_pull_statement,
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                            f"arn:aws:bedrock:*::foundation-model/amazon.nova-*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                ]),
            },
        )

        # Outputs
        self.multi_agent_image_uri = multi_agent_image.image_uri
        self.rag_query_image_uri = rag_query_image.image_uri
        self.multi_agent_role_arn = multi_agent_role.role_arn
        self.rag_query_role_arn = rag_query_role.role_arn
        self.gateway_role_arn = gateway_role.role_arn

        CfnOutput(self, f"multi-agent-image-{env_name}",
                  value=multi_agent_image.image_uri,
                  description="Multi-Agent container image URI")
        CfnOutput(self, f"rag-query-image-{env_name}",
                  value=rag_query_image.image_uri,
                  description="RAG Query container image URI")
        CfnOutput(self, f"multi-agent-role-{env_name}",
                  value=multi_agent_role.role_arn,
                  description="Multi-Agent IAM role ARN")
        CfnOutput(self, f"rag-query-role-{env_name}",
                  value=rag_query_role.role_arn,
                  description="RAG Query IAM role ARN")
        CfnOutput(self, f"gateway-role-{env_name}",
                  value=gateway_role.role_arn,
                  description="Web Search Gateway service role ARN")

        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5",
                reason="Global inference profile requires wildcard region for foundation model ARN"),
        ])
