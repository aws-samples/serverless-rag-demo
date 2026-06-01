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

        # IAM role for Multi-Agent runtime
        multi_agent_role = iam.Role(
            self, f"srd-multi-agent-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            ),
            inline_policies={
                "MultiAgentPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}",
                            f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:PutObject", "s3:GetObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/*"],
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
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}",
                            f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6-v1:0",
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

        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5",
                reason="Global inference profile requires wildcard region for foundation model ARN"),
        ])
