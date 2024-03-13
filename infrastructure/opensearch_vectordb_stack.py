import os
from aws_cdk import (
    NestedStack,
    aws_opensearchserverless as _oss,
    Tag as _tags,
    CfnOutput as _output,
    Aspects
)
from constructs import Construct
import os
import cdk_nag as _cdk_nag
from cdk_nag import NagSuppressions, NagPackSuppression

class OpensearchVectorDbStack(NestedStack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())
        env_name = self.node.try_get_context('environment_name')
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region=os.getenv('CDK_DEFAULT_REGION')
        collection_name = env_params['collection_name']
        index_name = env_params['index_name']
        lambda_role_arn = f"arn:aws:iam::{account_id}:role/{env_params['lambda_role_name']}_{region}"
        encryption_policy = _oss.CfnSecurityPolicy(self, f'sample-vectordb-encrypt-{env_name}',  name=f'sample-vectordb-encryption-{env_name}',
                                type='encryption',
                                policy="""{\"Rules\":[{\"ResourceType\":\"collection\",\"Resource\":[\"collection/"""+ collection_name +"""\"]}],\"AWSOwnedKey\":true}""")
        
        network_policy = _oss.CfnSecurityPolicy(self, f'sample-vectordb-nw-{env_name}', 
                                                name=f'sample-vectordb-nw-{env_name}',
                                type='network',
                                policy="""[{\"Rules\":[{\"ResourceType\":\"collection\",\"Resource\":[\"collection/"""+ collection_name + """\"]}, {\"ResourceType\":\"dashboard\",\"Resource\":[\"collection/"""+ collection_name + """\"]}],\"AllowFromPublic\":true}]""")

        data_access_policy = _oss.CfnAccessPolicy(self, f'sample-vectordb-data-{env_name}', name=f'sample-vectordb-data-{env_name}',
                                type='data',
                                policy="""[{\"Rules\":[{\"ResourceType\":\"index\",\"Resource\":[\"index/"""+ collection_name +"""/*\"], \"Permission\": [\"aoss:*\"]}, {\"ResourceType\":\"collection\",\"Resource\":[\"collection/"""+ collection_name +"""\"], \"Permission\": [\"aoss:*\"]}], \"Principal\": [\"""" + lambda_role_arn + """\"]}]""")
        
        cfn_collection = _oss.CfnCollection(self, f"vector_db_collection_{env_name}",
            name=collection_name,
            # the properties below are optional
            description="Serverless vector db example",
            type="VECTORSEARCH"
        )
        cfn_collection.add_dependency(encryption_policy)
        cfn_collection.add_dependency(network_policy)
        cfn_collection.add_dependency(data_access_policy)

        _output(self, f'collection_endpoint_{env_name}',
                value=cfn_collection.attr_collection_endpoint,
                description='Collection Endpoint',
                export_name='collection-endpoint-url'
                )
        
        print(cfn_collection.attr_collection_endpoint)
        
