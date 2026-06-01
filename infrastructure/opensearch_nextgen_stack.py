import json
import os
from aws_cdk import (
    Stack,
    Duration,
    aws_opensearchserverless as _oss,
    aws_iam as iam,
    aws_lambda as _lambda,
    CfnOutput,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class OpensearchNextgenStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, *, kb_role_arn: str = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")

        collection_name = env_params["collection_name"]
        ocu_mode = env_params.get("ocu_mode", "demo")  # noqa: F841 — reserved for future use

        # Index creator role — created BEFORE collection (uses * resource to avoid circular dep)
        index_creator_role = iam.Role(
            self, f"srd-index-creator-role-{env_name}",
            role_name=f"srd-index-creator-{env_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
            inline_policies={
                "AOSSAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["aoss:APIAccessAll"],
                        resources=["*"],
                    ),
                ]),
            },
        )

        # Encryption policy
        encryption_policy = _oss.CfnSecurityPolicy(
            self, f"srd-encrypt-{env_name}",
            name=f"srd-encrypt-{env_name}",
            type="encryption",
            policy=json.dumps({
                "Rules": [{"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]}],
                "AWSOwnedKey": True,
            }),
        )

        # Network policy (allow public access for demo)
        network_policy = _oss.CfnSecurityPolicy(
            self, f"srd-network-{env_name}",
            name=f"srd-network-{env_name}",
            type="network",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]},
                    {"ResourceType": "dashboard", "Resource": [f"collection/{collection_name}"]},
                ],
                "AllowFromPublic": True,
            }]),
        )

        # Data access policy — index creator Lambda role + KB role
        kb_role_arn_str = kb_role_arn or f"arn:aws:iam::{account_id}:role/srd-kb-role-{env_name}"
        principals = [
            index_creator_role.role_arn,
            kb_role_arn_str,
        ]

        data_access_policy = _oss.CfnAccessPolicy(
            self, f"srd-data-{env_name}",
            name=f"srd-data-{env_name}",
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "index", "Resource": [f"index/{collection_name}/*"], "Permission": ["aoss:*"]},
                    {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"], "Permission": ["aoss:*"]},
                ],
                "Principal": principals,
            }]),
        )

        # Collection (NextGen: no engine/method params needed — auto-configured)
        cfn_collection = _oss.CfnCollection(
            self, f"srd-collection-{env_name}",
            name=collection_name,
            type="VECTORSEARCH",
            description="Serverless RAG Demo v2 vector store",
        )
        cfn_collection.add_dependency(encryption_policy)
        cfn_collection.add_dependency(network_policy)
        cfn_collection.add_dependency(data_access_policy)

        # Index creator Lambda — invoked by deploy.sh AFTER stack completes (not as custom resource)
        index_creator_fn = _lambda.Function(
            self, f"srd-index-creator-fn-{env_name}",
            function_name=f"srd-index-creator-{env_name}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.on_event",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "custom_resources", "aoss_index")
            ),
            timeout=Duration.minutes(5),
            role=index_creator_role,
            environment={
                "COLLECTION_ENDPOINT": cfn_collection.attr_collection_endpoint,
            },
        )

        # Outputs
        self.collection_endpoint = cfn_collection.attr_collection_endpoint
        self.collection_arn = cfn_collection.attr_arn
        self.collection_name = collection_name

        CfnOutput(self, f"collection-endpoint-{env_name}",
                  value=cfn_collection.attr_collection_endpoint,
                  description="AOSS NextGen Collection Endpoint")
        CfnOutput(self, f"index-creator-fn-{env_name}",
                  value=index_creator_fn.function_name,
                  description="Lambda to create AOSS index")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM4", reason="Lambda basic execution managed policy required"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5", reason="AOSS APIAccessAll needs * to avoid circular dependency with collection"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-L1", reason="Python 3.12 is current"),
        ])
