import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_iam as iam,
    aws_s3 as s3,
    aws_bedrock as bedrock,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class KnowledgeBaseStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        collection_arn: str,
        collection_endpoint: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        kb_name = env_params["knowledge_base_name"]
        index_name = env_params["index_name"]
        embed_model_id = env_params["embed_model_id"]
        bucket_name = env_params["s3_data_bucket"]

        # S3 data bucket for documents
        data_bucket = s3.Bucket(
            self, f"srd-data-bucket-{env_name}",
            bucket_name=f"{bucket_name}-{account_id}-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
            cors=[s3.CorsRule(
                allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.GET],
                allowed_origins=["*"],
                allowed_headers=["*"],
            )],
        )

        # KB execution role
        kb_role = iam.Role(
            self, f"srd-kb-role-{env_name}",
            role_name=f"srd-kb-role-{env_name}",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "BedrockKBPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["aoss:APIAccessAll"],
                        resources=[collection_arn],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=[f"arn:aws:bedrock:{region}::foundation-model/{embed_model_id}"],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:ListBucket"],
                        resources=[data_bucket.bucket_arn, f"{data_bucket.bucket_arn}/*"],
                    ),
                ]),
            },
        )

        # Bedrock Knowledge Base (L1 construct)
        kb = bedrock.CfnKnowledgeBase(
            self, f"srd-kb-{env_name}",
            name=kb_name,
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{region}::foundation-model/{embed_model_id}",
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=collection_arn,
                    vector_index_name=index_name,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field="embedding",
                        text_field="text",
                        metadata_field="metadata",
                    ),
                ),
            ),
        )

        # S3 Data Source
        data_source = bedrock.CfnDataSource(
            self, f"srd-kb-datasource-{env_name}",
            knowledge_base_id=kb.attr_knowledge_base_id,
            name=f"srd-docs-{env_name}",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=data_bucket.bucket_arn,
                ),
            ),
        )

        # Outputs
        self.knowledge_base_id = kb.attr_knowledge_base_id
        self.data_source_id = data_source.attr_data_source_id
        self.data_bucket = data_bucket
        self.data_bucket_name = data_bucket.bucket_name

        CfnOutput(self, f"kb-id-{env_name}",
                  value=kb.attr_knowledge_base_id,
                  description="Bedrock Knowledge Base ID")
        CfnOutput(self, f"data-bucket-{env_name}",
                  value=data_bucket.bucket_name,
                  description="Document upload bucket")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5", reason="KB role needs wildcard for S3 objects"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-S1", reason="Access logs not required for demo data bucket"),
        ])
