from aws_cdk import (
    Stack,
    NestedStack,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct
import os

class Storage_Stack(NestedStack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")
        region=os.getenv('CDK_DEFAULT_REGION')
        account_id = os.getenv('CDK_DEFAULT_ACCOUNT')
        self.indx_dynamodb = dynamodb.Table(self,
                                                 id=f'rag-llm-dynm-indx-{env_name}',
                                                 table_name=self.node.try_get_context(env_name)['index_dynamo_table_name'],
                                                 partition_key=dynamodb.Attribute(name="prim_key",
                                                                                  type=dynamodb.AttributeType.STRING),
                                                 sort_key=dynamodb.Attribute(name="sort_key",
                                                                             type=dynamodb.AttributeType.STRING))
        # add auto scaling policy for dynamodb read and write
        read_scaling_indx = self.indx_dynamodb.auto_scale_read_capacity(min_capacity=5, max_capacity=50)
        read_scaling_indx.scale_on_utilization(
            target_utilization_percent=75
        )

        write_scaling_indx = self.indx_dynamodb.auto_scale_write_capacity(min_capacity=5, max_capacity=50)
        write_scaling_indx.scale_on_utilization(
            target_utilization_percent=75
        )

        self.conversations_dynamodb = dynamodb.Table(self,
                                                 id=f'rag-llm-dynm-conv-{env_name}',
                                                 table_name=self.node.try_get_context(env_name)['conversations_dynamo_table_name'],
                                                 partition_key=dynamodb.Attribute(name="prim_key",
                                                                                  type=dynamodb.AttributeType.STRING),
                                                 sort_key=dynamodb.Attribute(name="sort_key",
                                                                             type=dynamodb.AttributeType.STRING))
        # add auto scaling policy for dynamodb read and write
        read_scaling_conv = self.conversations_dynamodb.auto_scale_read_capacity(min_capacity=5, max_capacity=50)
        read_scaling_conv.scale_on_utilization(
            target_utilization_percent=75
        )

        write_scaling_conv = self.conversations_dynamodb.auto_scale_write_capacity(min_capacity=5, max_capacity=50)
        write_scaling_conv.scale_on_utilization(
            target_utilization_percent=75
        )

    

        