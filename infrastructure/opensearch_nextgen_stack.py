import json
import os
from aws_cdk import (
    NestedStack,
    aws_opensearchserverless as _oss,
    CfnOutput,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class OpensearchNextgenStack(NestedStack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION")

        collection_name = env_params["collection_name"]
        # NOTE: CfnCollectionGroup is not available in the current CDK version.
        # The group_name and ocu_mode context params are retained for future use
        # when CfnCollectionGroup lands in aws-cdk-lib.
        ocu_mode = env_params.get("ocu_mode", "demo")  # noqa: F841 — reserved for future use

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

        # Data access policy
        data_access_policy = _oss.CfnAccessPolicy(
            self, f"srd-data-{env_name}",
            name=f"srd-data-{env_name}",
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "index", "Resource": [f"index/{collection_name}/*"], "Permission": ["aoss:*"]},
                    {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"], "Permission": ["aoss:*"]},
                ],
                "Principal": [f"arn:aws:iam::{account_id}:root"],
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

        # Outputs
        self.collection_endpoint = cfn_collection.attr_collection_endpoint
        self.collection_arn = cfn_collection.attr_arn
        self.collection_name = collection_name

        CfnOutput(self, f"collection-endpoint-{env_name}",
                  value=cfn_collection.attr_collection_endpoint,
                  description="AOSS NextGen Collection Endpoint")
