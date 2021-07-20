from typing import Optional

from aws_cdk.aws_dynamodb import Table
from aws_cdk.aws_iam import Effect, PolicyDocument, PolicyStatement, Role, ServicePrincipal
from aws_cdk.aws_kms import Key
from aws_cdk.aws_lambda import Code, Function, Runtime, SingletonFunction, StartingPosition
from aws_cdk.aws_lambda_event_sources import DynamoEventSource
from aws_cdk.aws_logs import RetentionDays
from aws_cdk.core import Construct, CustomResource, Duration, RemovalPolicy
from b_cfn_elasticsearch_index.resource import ElasticsearchIndexResource
from b_elasticsearch_layer.layer import Layer as BElasticsearchLayer

from b_cfn_elasticsearch_cloner.cloner_source import root as cloner_root
from b_cfn_elasticsearch_cloner.initial_cloner_source import root as initial_cloner_root


class ElasticsearchCloner(Construct):
    """
    Custom resource used for managing an Elasticsearch cloner.

    Creates a cloner and clones existing data on stack creation.
    Updates the cloner on settings change.
    Deletes the cloner on stack deletion.

    :param embeddings_key: Elasticsearch mapping properties name (field name),
        where knn dense vector of sentence embeddings are stored.
    :param sagemaker_endpoint_name: The name of Sagemaker inference endpoint used to provide NLP features.
    :param sagemaker_embeddings_key: Key under which embeddings are received in Sagemaker response.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        elasticsearch_index: ElasticsearchIndexResource,
        dynamodb_table: Table,
        kms_key: Optional[Key] = None,
        sagemaker_endpoint_name: str = None,
        sagemaker_embeddings_key: str = None,
        sagemaker_arn: str = None
    ) -> None:
        super().__init__(scope=scope, id=id)

        elasticsearch_layer = BElasticsearchLayer(scope=self, name=f"{id}ElasticsearchLayer")

        if bool(sagemaker_endpoint_name) ^ bool(sagemaker_embeddings_key):
            raise ValueError(
                f'In order to use sentence embedding, all of the following enviroment variables are required: '
                f'SAGEMAKER_ENDPOINT_NAME, SAGEMAKER_EMBEDDINGS_KEY. '
                f'Else provide none of above.'
            )

        optional_sagemaker_parameters = {
            'SAGEMAKER_ENDPOINT_NAME': sagemaker_endpoint_name or None,
            'SAGEMAKER_EMBEDDINGS_KEY': sagemaker_embeddings_key or None
        }

        initial_cloner_function = SingletonFunction(
            scope=self,
            id='InitialClonerFunction',
            uuid='e01116a4-f939-43f2-8f5b-cc9f862c9e01',
            lambda_purpose='InitialClonerSingletonLambda',
            code=Code.from_asset(initial_cloner_root),
            handler='index.handler',
            runtime=Runtime.PYTHON_3_8,
            layers=[elasticsearch_layer],
            log_retention=RetentionDays.ONE_MONTH,
            memory_size=128,
            timeout=Duration.minutes(15),
            role=Role(
                scope=self,
                id='InitialClonerFunctionRole',
                assumed_by=ServicePrincipal('lambda.amazonaws.com'),
                inline_policies={
                    'LogsPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=[
                                    'logs:CreateLogGroup',
                                    'logs:CreateLogStream',
                                    'logs:PutLogEvents',
                                    'logs:DescribeLogStreams',
                                ],
                                resources=['arn:aws:logs:*:*:*'],
                                effect=Effect.ALLOW,
                            )
                        ]
                    ),
                    'ElasticsearchPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=[
                                    'es:ESHttpDelete',
                                    'es:ESHttpGet',
                                    'es:ESHttpHead',
                                    'es:ESHttpPatch',
                                    'es:ESHttpPost',
                                    'es:ESHttpPut',
                                ],
                                resources=['*'],
                                effect=Effect.ALLOW,
                            )
                        ]
                    ),
                    'DynamodbPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=['dynamodb:*'],
                                resources=['*'],
                                effect=Effect.ALLOW,
                            )
                        ]
                    ),
                },
                description='Role for DynamoDB Initial Cloner Function',
            ),
        )

        if kms_key:
            initial_cloner_function.add_to_role_policy(
                PolicyStatement(
                    actions=['kms:Decrypt'],
                    resources=[kms_key.key_arn],
                    effect=Effect.ALLOW,
                ),
            )

        initial_cloner = CustomResource(
            scope=self,
            id='InitialCloner',
            service_token=initial_cloner_function.function_arn,
            removal_policy=RemovalPolicy.DESTROY,
            properties={
                'DynamodbTableName': dynamodb_table.table_name,
                'ElasticsearchIndexName': elasticsearch_index.index_name,
                'ElasticsearchEndpoint': elasticsearch_index.elasticsearch_domain.domain_endpoint,
            },
            resource_type='Custom::ElasticsearchInitialCloner',
        )

        primary_key_field = initial_cloner.get_att_string('PrimaryKeyField')

        dynamodb_stream_arn = dynamodb_table.table_stream_arn
        if not dynamodb_stream_arn:
            raise Exception('DynamoDB streams must be enabled for the table')

        dynamodb_event_source = DynamoEventSource(
            table=dynamodb_table,
            starting_position=StartingPosition.LATEST,
            enabled=True,
            max_batching_window=Duration.seconds(10),
            bisect_batch_on_error=True,
            parallelization_factor=2,
            batch_size=1000,
            retry_attempts=10,
        )

        cloner_function = Function(
            scope=self,
            id='ClonerFunction',
            code=Code.from_asset(cloner_root),
            handler='index.handler',
            runtime=Runtime.PYTHON_3_8,
            environment={
                'ES_INDEX_NAME': elasticsearch_index.index_name,
                'ES_DOMAIN_ENDPOINT': elasticsearch_index.elasticsearch_domain.domain_endpoint,
                'PRIMARY_KEY_FIELD': primary_key_field,
                **{
                    k: optional_sagemaker_parameters[k] for k in optional_sagemaker_parameters
                    if all(optional_sagemaker_parameters.values())
                }
            },
            events=[dynamodb_event_source],
            layers=[elasticsearch_layer],
            log_retention=RetentionDays.ONE_MONTH,
            memory_size=128,
            role=Role(
                scope=self,
                id='ClonerFunctionRole',
                assumed_by=ServicePrincipal('lambda.amazonaws.com'),
                inline_policies={
                    'LogsPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=[
                                    'logs:CreateLogGroup',
                                    'logs:CreateLogStream',
                                    'logs:PutLogEvents',
                                    'logs:DescribeLogStreams',
                                ],
                                resources=['arn:aws:logs:*:*:*'],
                                effect=Effect.ALLOW,
                            )
                        ]
                    ),
                    'ElasticsearchPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=[
                                    'es:ESHttpDelete',
                                    'es:ESHttpGet',
                                    'es:ESHttpHead',
                                    'es:ESHttpPatch',
                                    'es:ESHttpPost',
                                    'es:ESHttpPut',
                                ],
                                resources=[f'{elasticsearch_index.elasticsearch_domain.domain_arn}/*'],
                                effect=Effect.ALLOW,
                            )
                        ]
                    ),
                    'DynamodbStreamsPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=[
                                    'dynamodb:DescribeStream',
                                    'dynamodb:GetRecords',
                                    'dynamodb:GetShardIterator',
                                    'dynamodb:ListStreams',
                                ],
                                resources=[dynamodb_stream_arn],
                                effect=Effect.ALLOW,
                            )
                        ]
                    ),
                    'SagemakerPolicy': PolicyDocument(
                        statements=[
                            PolicyStatement(
                                actions=[
                                    'sagemaker:InvokeEndpoint'
                                ],
                                resources=[sagemaker_arn],
                                effect=Effect.ALLOW
                            )
                        ]
                    ),
                },
                description='Role for DynamoDB Cloner Function',
            ),
            timeout=Duration.seconds(30),
        )

        if kms_key:
            cloner_function.add_to_role_policy(
                PolicyStatement(
                    actions=['kms:Decrypt'],
                    resources=[kms_key.key_arn],
                    effect=Effect.ALLOW,
                ),
            )
