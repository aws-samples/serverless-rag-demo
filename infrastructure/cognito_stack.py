import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    aws_cognito as cognito,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class CognitoStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)

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

        # Outputs
        self.user_pool_id = user_pool.user_pool_id
        self.client_id = user_pool_client.user_pool_client_id

        CfnOutput(self, f"user-pool-id-{env_name}", value=user_pool.user_pool_id)
        CfnOutput(self, f"client-id-{env_name}", value=user_pool_client.user_pool_client_id)

        # Nag suppressions
        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG1", reason="Password policy configured above"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG2", reason="MFA not needed for demo"),
            _cdk_nag.NagPackSuppression(id="AwsSolutions-COG8", reason="Plus tier not needed for demo"),
        ])
