import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import boto3
from elasticsearch import Elasticsearch, RequestsHttpConnection
from elasticsearch.helpers import bulk
from elasticsearch.serializer import JSONSerializer
from requests_aws4auth import AWS4Auth

logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")


class Action:
    """
    This custom resource handles initial data cloning to Elasticsearch.
    Clones the data on creation, clones the data if DynamoDB table has changed, otherwise does nothing.
    """

    def __init__(self, invocation_event: Dict[str, Any]):
        self.__invocation_event: Dict[str, Any] = invocation_event
        self.__parameters: Dict[str, Any] = invocation_event["ResourceProperties"]
        self.__old_parameters: Optional[Dict[str, Any]] = invocation_event.get('OldResourceProperties')

        try:
            self.REGION = os.environ["AWS_REGION"]

            self.TABLE_NAME = self.__parameters["DynamodbTableName"]
            self.ELASTICSEARCH_ENDPOINT = self.__parameters["ElasticsearchEndpoint"]
            self.INDEX_NAME = self.__parameters["ElasticsearchIndexName"]
        except KeyError as ex:
            logger.error(f"Missing environment: {repr(ex)}.")
            raise

    def create(self) -> Tuple[Optional[Dict[Any, Any]], Optional[str]]:
        """
        Clones existing DynamoDB table data to an Elasticsearch index.

        :return: A tuple containing two items:
            1. Custom data to return back to CloudFormation service.
            2. Physical resource id (can be empty).
        """
        logger.info(f"Initiating resource creation with these parameters: {json.dumps(self.__parameters)}.")

        credentials = boto3.Session().get_credentials()
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            self.REGION,
            "es",
            session_token=credentials.token,
        )

        class DynamodbEncoder(JSONSerializer):
            def default(self, data):
                if isinstance(data, set):
                    return list(data)
                if isinstance(data, Decimal):
                    return float(data)
                return JSONSerializer.default(self, data)

        es = Elasticsearch(
            hosts=[{"host": self.ELASTICSEARCH_ENDPOINT, "port": 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            serializer=DynamodbEncoder(),
        )

        dynamodb_table = dynamodb.Table(self.TABLE_NAME)

        id_field = self.__get_dynamodb_primary_key(dynamodb_table)

        bulk(
            es,
            self.__elasticsearch_index_iterator(id_field, self.INDEX_NAME, self.__dynamodb_iterator(dynamodb_table)),
            raise_on_error=False,
            raise_on_exception=False,
        )

        return {"PrimaryKeyField": self.__get_dynamodb_primary_key(dynamodb_table)}, None

    def update(self) -> Tuple[Optional[Dict[Any, Any]], Optional[str]]:
        """
        Clones the existing DynamoDB data to the Elasticsearch index, since one of them has changed.

        :return: A tuple containing two items:
            1. Custom data to return back to CloudFormation service.
            2. Physical resource id (can be empty).
        """
        logger.info(f"Initiating resource update with these parameters: {json.dumps(self.__parameters)}.")

        return self.create()

    def delete(self) -> Tuple[Optional[Dict[Any, Any]], Optional[str]]:
        """
        Does nothing.

        :return: A tuple containing two items:
            1. Custom data to return back to CloudFormation service.
            2. Physical resource id (can be empty).
        """
        logger.info(f"Initiating resource deletion with these parameters: {json.dumps(self.__parameters)}.")

        dynamodb_table = dynamodb.Table(self.TABLE_NAME)

        return {"PrimaryKeyField": self.__get_dynamodb_primary_key(dynamodb_table)}, None

    def __dynamodb_iterator(self, dynamodb_table):
        table_finished = False
        start_key = None
        while not table_finished:
            scan_args = {}
            if start_key:
                scan_args["ExclusiveStartKey"] = start_key
            scan_response = dynamodb_table.scan(**scan_args)
            for item in scan_response["Items"]:
                yield item
            if "LastEvaluatedKey" in scan_response:
                start_key = scan_response["LastEvaluatedKey"]
            else:
                table_finished = True

    def __elasticsearch_index_iterator(self, id_field, es_index, items_iterator):
        for item in items_iterator:
            action = {
                "_op_type": "index",
                "_index": es_index,
                "_id": item[id_field],
                "_source": item,
            }
            yield action

    def __get_dynamodb_primary_key(self, dynamodb_table):
        for key in dynamodb_table.key_schema:
            if key["KeyType"] == "HASH":
                return key["AttributeName"]
        # Should never happen, but just in case.
        raise Exception("Could not find a DynamoDB primary key")
