import logging
import os
from typing import Any, Dict

import boto3
from elasticsearch import Elasticsearch, RequestsHttpConnection
from elasticsearch.helpers import bulk
from requests_aws4auth import AWS4Auth

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from dynamodb_decode import DynamodbDecoder
except ImportError as ex:
    logger.exception("Failed import.")
    from b_cfn_elasticsearch_cloner.cloner_source.dynamodb_decode import DynamodbDecoder


es_index = os.environ["ES_INDEX_NAME"]
es_endpoint = os.environ["ES_DOMAIN_ENDPOINT"]
primary_key_field = os.environ["PRIMARY_KEY_FIELD"]
region = os.environ["AWS_REGION"]


credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    region,
    "es",
    session_token=credentials.token,
)

es = Elasticsearch(
    hosts=[{"host": es_endpoint, "port": 443}],
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

    logger.info("Starting processing DynamoDB events.")

    # Send data to elasticsearch using bulk API.
    succeeded, failed = bulk(
        es,
        dynamodb_to_es_generator(event),
        stats_only=True,
        raise_on_error=False,
        raise_on_exception=False,
    )

    logger.info(f"Finished processing DynamoDB events. Succeeded: {succeeded}, failed: {failed}")


def dynamodb_to_es_generator(event: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    Converts events form DynamoDB streams into a format suitable for Elasticsearch's bulk API.
    """
    for record in event["Records"]:
        try:
            if record["eventName"] == "INSERT":
                item = DynamodbDecoder.decode_json(record["dynamodb"]["NewImage"])
                yield {
                    "_op_type": "index",
                    "_index": es_index,
                    "_id": item[primary_key_field],
                    "_source": item,
                }
            elif record["eventName"] == "MODIFY":
                item = DynamodbDecoder.decode_json(record["dynamodb"]["NewImage"])

                yield {
                    "_op_type": "index",
                    "_index": es_index,
                    "_id": item[primary_key_field],
                    "_source": item,
                }
            elif record["eventName"] == "REMOVE":
                item = DynamodbDecoder.decode_json(record["dynamodb"]["NewImage"])

                yield {
                    "_op_type": "delete",
                    "_index": es_index,
                    "_id": item[primary_key_field],
                }
        except Exception:
            logger.exception(f"Failed to process record {record}.")
            # Don't hold up everything for a single error.
            continue
