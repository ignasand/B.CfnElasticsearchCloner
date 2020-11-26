import json
import logging
from typing import Any, Dict, Optional, Tuple

import boto3
import botocore
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

try:
    from action import Action
    from cfnresponse import CfnResponse
except ImportError as ex:
    logger.exception("Failed import.")
    from b_cfn_twilio_activity.source.action import Action
    from b_cfn_twilio_activity.source.cfnresponse import CfnResponse

logger.info(f"Version of boto3 lib: {boto3.__version__}.")
logger.info(f"Version of botocore lib: {botocore.__version__}.")


def __handle(event, context) -> Tuple[Optional[Dict[Any, Any]], Optional[str]]:
    """
    Handles incoming event by invoking a specific action according to a request type.

    :param event: Invocation event.
    :param context: Invocation context.

    :return: A tuple containing two items:
        1. Custom data to return back to CloudFormation service (can be empty).
        2. Physical resource id (can be empty).
    """
    serialized_event = json.dumps(event, default=lambda o: "<not serializable>")
    logger.info(f"Got new request. Event: {serialized_event}.")

    action = Action(event)

    if event["RequestType"] == "Create":
        return action.create()

    if event["RequestType"] == "Update":
        return action.update()

    if event["RequestType"] == "Delete":
        return action.delete()

    raise KeyError("Unsupported request type! Type: {}".format(event["RequestType"]))


def handler(event, context) -> None:
    """
    Handles incoming event.

    :param event: Invocation event.
    :param context: Invocation context.

    :return: No return.
    """
    response = CfnResponse(event, context)

    try:
        data, resource_id = __handle(event, context)
        response.respond(CfnResponse.CfnResponseStatus.SUCCESS, data=data, resource_id=resource_id)
    except ClientError as ex:
        err_msg = f"{repr(ex)}:{ex.response}"
        response.respond(CfnResponse.CfnResponseStatus.FAILED, status_reason=err_msg)
    except Exception as ex:
        response.respond(CfnResponse.CfnResponseStatus.FAILED, status_reason=repr(ex))
