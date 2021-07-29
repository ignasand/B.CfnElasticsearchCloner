import logging
import os
from typing import Any, Dict, List, Generator
import json

import boto3
from elasticsearch import Elasticsearch, RequestsHttpConnection
from elasticsearch.helpers import bulk
from requests_aws4auth import AWS4Auth

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from dynamodb_decode import DynamodbDecoder
except ImportError as ex:
    logger.exception('Failed import.')
    from b_cfn_elasticsearch_cloner.cloner_source.dynamodb_decode import DynamodbDecoder

ES_INDEX = os.environ['ES_INDEX_NAME']
ES_ENDPOINT = os.environ['ES_DOMAIN_ENDPOINT']
PRIMARY_KEY_FIELD = os.environ['PRIMARY_KEY_FIELD']

SAGEMAKER_ENDPOINT_NAME = os.environ.get('SAGEMAKER_ENDPOINT_NAME')
SAGEMAKER_EMBEDDINGS_KEY = os.environ.get('SAGEMAKER_EMBEDDINGS_KEY')

boto3_session = boto3.Session()
sagemaker_client = boto3_session.client('sagemaker-runtime')
credentials = boto3_session.get_credentials()

awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    boto3_session.region_name,
    'es',
    session_token=credentials.token,
)

es = Elasticsearch(
    hosts=[{'host': ES_ENDPOINT, 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)


def handler(event: Dict[Any, Any], context: Any) -> None:
    """
    Handles incoming DynamoDB stream events.

    :param event: Invocation event.
    :param context: Invocation context.

    :return: No return.
    """

    logger.info('Starting processing DynamoDB events.')

    use_embeddings = bool(SAGEMAKER_EMBEDDINGS_KEY and SAGEMAKER_ENDPOINT_NAME)

    if not use_embeddings and any([SAGEMAKER_EMBEDDINGS_KEY, SAGEMAKER_ENDPOINT_NAME]):
        raise OSError(
            f'In order to use sentence embedding, all of the following enviroment variables are required: '
            f'SAGEMAKER_ENDPOINT_NAME, SAGEMAKER_EMBEDDINGS_KEY. '
            f'Else provide none of above.'
        )

    # Send data to elasticsearch using bulk API.
    succeeded, failed = bulk(
        es,
        dynamodb_to_es_generator(event, use_embeddings),
        stats_only=True,
        raise_on_error=False,
        raise_on_exception=False,
    )

    logger.info(f'Finished processing DynamoDB events. Succeeded: {succeeded}, failed: {failed}')


def get_sm_features(source: str, sagemaker_client: Any, endpoint_name: str) -> Dict[str, Any]:
    sagemaker_response = sagemaker_client.invoke_endpoint(
        EndpointName=endpoint_name,
        Body=source.encode(encoding='utf-8'),
        ContentType='text/plain'
    )
    source_features = json.loads(sagemaker_response['Body'].read().decode())
    return source_features


def get_embeddings(source: str) -> List[float]:
    logger.info(f'Performing embeddings.')
    source_features = get_sm_features(
        source, sagemaker_client=sagemaker_client, endpoint_name=SAGEMAKER_ENDPOINT_NAME)
    embeddings = source_features[SAGEMAKER_EMBEDDINGS_KEY]
    return embeddings


def dynamodb_to_es_generator(
        event: Dict[Any, Any],
        use_embeddings: bool = False
) -> Generator[Dict[str, Any], None, None]:
    """
    Converts events form DynamoDB streams into a format suitable for Elasticsearch's bulk API.
    """

    for record in event['Records']:
        try:
            if record['eventName'] == 'INSERT':
                item = DynamodbDecoder.decode_json(record['dynamodb']['NewImage'])
                if use_embeddings:
                    item['question_embedding'] = get_embeddings(item['question'])

                yield {
                    '_op_type': 'index',
                    '_index': ES_INDEX,
                    '_id': item[PRIMARY_KEY_FIELD],
                    '_source': item,
                }
            elif record['eventName'] == 'MODIFY':
                item = DynamodbDecoder.decode_json(record['dynamodb']['NewImage'])
                if use_embeddings:
                    item['question_embedding'] = get_embeddings(item['question'])

                yield {
                    '_op_type': 'index',
                    '_index': ES_INDEX,
                    '_id': item[PRIMARY_KEY_FIELD],
                    '_source': item,
                }
            elif record['eventName'] == 'REMOVE':
                item = DynamodbDecoder.decode_json(record['dynamodb']['Keys'])
                yield {
                    '_op_type': 'delete',
                    '_index': ES_INDEX,
                    '_id': item[PRIMARY_KEY_FIELD],
                }
        except Exception:
            logger.error(f'Failed to process record {record}.')
            # Don't hold up everything for a single error.
            continue
