import json
import os
import subprocess
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


def _build_ui(source_path: str) -> str:
    """Build React UI locally and return the output directory path."""
    subprocess.run(["npm", "install"], cwd=source_path, check=True, capture_output=True)
    subprocess.run(["npm", "run", "build"], cwd=source_path, check=True, capture_output=True)
    # Vite outputs to dist/
    dist_dir = os.path.join(source_path, "dist")
    if os.path.isdir(dist_dir):
        return dist_dir
    # CRA fallback
    build_dir = os.path.join(source_path, "build")
    if os.path.isdir(build_dir):
        return build_dir
    raise RuntimeError(f"No build output found in {source_path}. Run 'npm run build' manually.")


class CloudFrontHostingStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        cognito_user_pool_id: str,
        cognito_client_id: str,
        rest_endpoint_url: str,
        websocket_url: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        # S3 bucket for static hosting
        site_bucket = s3.Bucket(
            self, f"srd-ui-bucket-{env_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # CloudFront distribution with S3 origin
        distribution = cloudfront.Distribution(
            self, f"srd-distribution-{env_name}",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # Build React UI locally and deploy to S3 (no Docker needed)
        chat_ui_path = os.path.join(os.getcwd(), "artifacts/chat-ui")
        bundling_stacks = self.node.try_get_context("aws:cdk:bundling-stacks")
        skip_bundling = bundling_stacks == []

        if not skip_bundling:
            build_output = _build_ui(chat_ui_path)
            ui_source = s3_deploy.Source.asset(build_output)
        else:
            # During tests, use the source dir as-is (no build step)
            ui_source = s3_deploy.Source.asset(chat_ui_path)

        s3_deploy.BucketDeployment(
            self, f"srd-ui-deploy-{env_name}",
            sources=[ui_source],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # Deploy runtime-config.json separately
        runtime_config = {
            "cognitoUserPoolId": cognito_user_pool_id,
            "cognitoClientId": cognito_client_id,
            "cognitoRegion": region,
            "restEndpointUrl": rest_endpoint_url,
            "websocketUrl": websocket_url,
        }

        s3_deploy.BucketDeployment(
            self, f"srd-runtime-config-{env_name}",
            sources=[s3_deploy.Source.json_data("runtime-config.json", runtime_config)],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/runtime-config.json"],
        )

        # Outputs
        self.distribution_url = f"https://{distribution.distribution_domain_name}"
        CfnOutput(self, f"ui-url-{env_name}",
                  value=self.distribution_url,
                  description="CloudFront UI URL")

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR4", reason="Using default CloudFront certificate for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-S1", reason="Access logs not needed for demo UI bucket"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR1", reason="Geo restriction not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR2", reason="WAF not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-CFR3", reason="Access logging not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5", reason="BucketDeployment custom resource requires wildcard permissions"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM4", reason="BucketDeployment uses AWS managed Lambda execution policy"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-L1", reason="BucketDeployment Lambda runtime managed by CDK"),
        ])
