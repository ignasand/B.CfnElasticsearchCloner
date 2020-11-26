from aws_cdk.aws_dynamodb import Attribute, AttributeType, StreamViewType, Table
from aws_cdk.aws_ec2 import EbsDeviceVolumeType
from aws_cdk.aws_elasticsearch import CapacityConfig, Domain, EbsOptions, ElasticsearchVersion, ZoneAwarenessConfig
from aws_cdk.core import RemovalPolicy, Stack
from b_cfn_elasticsearch_index.resource import ElasticsearchIndexResource

from b_cfn_elasticsearch_cloner.resource import ElasticsearchCloner


class TestingInfrastructure(Stack):
    def __init__(self, scope: Stack):
        super().__init__(scope=scope, id=f"TestingStack", stack_name=f"TestingStack")

        table = Table(
            scope=self,
            id="TestingTable",
            partition_key=Attribute(name="id", type=AttributeType.STRING),
            stream=StreamViewType.NEW_IMAGE,
            removal_policy=RemovalPolicy.DESTROY,
        )

        domain = Domain(
            scope=self,
            id="TestingElasticsearchDomain",
            version=ElasticsearchVersion.V7_7,
            capacity=CapacityConfig(
                # Use the cheapest instance available.
                data_node_instance_type="t3.small.elasticsearch",
                data_nodes=1,
                master_nodes=None,
            ),
            zone_awareness=ZoneAwarenessConfig(enabled=False),
            ebs=EbsOptions(enabled=True, volume_size=10, volume_type=EbsDeviceVolumeType.GP2),
        )

        elasticsearch_index = ElasticsearchIndexResource(
            scope=self,
            name="TestingElasticsearchIndex",
            elasticsearch_domain=domain,
            index_prefix="testing_index",
        )

        elasticsearch_cloner = ElasticsearchCloner(
            scope=self,
            id="TestingElasticsearchCloner",
            elasticsearch_index=elasticsearch_index,
            dynamodb_table=table,
        )
