# infrastructure/hive_stack.py
import os
from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_kms as kms,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class HiveStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        cognito_identity_pool_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        # KMS key for encrypting user secrets
        hive_kms_key = kms.Key(
            self, f"srd-hive-key-{env_name}",
            alias=f"srd-hive-{env_name}",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Access logs bucket
        access_logs_bucket = s3.Bucket(
            self, f"srd-hive-logs-{env_name}",
            bucket_name=f"srd-hive-logs-{env_name}-{account_id}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # S3 bucket for per-user state
        state_bucket = s3.Bucket(
            self, f"srd-hive-state-{env_name}",
            bucket_name=f"srd-hive-state-{env_name}-{account_id}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=hive_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            server_access_logs_bucket=access_logs_bucket,
            server_access_logs_prefix="state-bucket-logs/",
        )

        # DynamoDB table for user -> container mapping
        user_table = dynamodb.Table(
            self, f"srd-hive-users-{env_name}",
            table_name=f"srd-hive-users-{env_name}",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        # Container image
        hive_image = ecr_assets.DockerImageAsset(
            self, f"srd-hive-image-{env_name}",
            directory=os.path.join(os.getcwd(), "containers/hive"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # IAM role for Hive runtime
        hive_role = iam.Role(
            self, f"srd-hive-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            ),
            inline_policies={
                "HivePolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "ecr:GetAuthorizationToken",
                            "ecr:BatchGetImage",
                            "ecr:GetDownloadUrlForLayer",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                        resources=[
                            state_bucket.bucket_arn,
                            f"{state_bucket.bucket_arn}/*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
                        resources=[hive_kms_key.key_arn],
                    ),
                    iam.PolicyStatement(
                        actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"],
                        resources=[user_table.table_arn],
                    ),
                ]),
            },
        )

        # Outputs
        self.hive_image_uri = hive_image.image_uri
        self.hive_role_arn = hive_role.role_arn
        self.state_bucket_name = state_bucket.bucket_name
        self.kms_key_id = hive_kms_key.key_id

        CfnOutput(self, f"hive-image-{env_name}",
                  value=hive_image.image_uri,
                  description="Hive container image URI")
        CfnOutput(self, f"hive-role-{env_name}",
                  value=hive_role.role_arn,
                  description="Hive IAM role ARN")
        CfnOutput(self, f"hive-state-bucket-{env_name}",
                  value=state_bucket.bucket_name,
                  description="Hive S3 state bucket")
        CfnOutput(self, f"hive-kms-key-{env_name}",
                  value=hive_kms_key.key_id,
                  description="Hive KMS key ID")

        _cdk_nag.NagSuppressions.add_resource_suppressions(access_logs_bucket, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-S1",
                reason="Access logs bucket does not need its own access logs (recursive)"),
        ])
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5",
                reason="ECR pull requires wildcard; S3 scoped to hive bucket"),
        ])
