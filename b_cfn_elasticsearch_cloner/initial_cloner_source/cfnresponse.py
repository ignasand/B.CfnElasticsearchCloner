import json
import logging
from enum import Enum
from typing import Any, Dict, Optional


class CfnResponse:
    """
    Class that sends response back to the CloudFormation service. Read more about responses here:
    https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref-responses.html
    """

    class CfnResponseStatus(Enum):
        """
        Enum class specifying possible states for a response status.
        """

        SUCCESS = "SUCCESS"
        FAILED = "FAILED"

    def __init__(self, invocation_event: Dict[str, Any], context: Any):
        """
        Constructor.

        :param invocation_event: Event dictionary that was passed to this lambda function.
        :param context: Lambda context that was passed to this lambda function.
        """
        self.__invocation_event = invocation_event
        self.__context = context

    def respond(
        self,
        status: CfnResponseStatus,
        status_reason: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        """
        Creates and sends response back to CloudFormation service.

        :param status: Operation status - failed or success.
        :param status_reason: Reason message for the status.
        :param data: Dictionary data to return back to CloudFormation.
        :param resource_id: Specify a custom id for a resource(s). This value should be an identifier unique to
        the custom resource vendor, and can be up to 1 Kb in size. The value must be a non-empty string and must
        be identical for all responses for the same resource.

        :return: No return.
        """
        response_body = dict(
            Status=status.value,
            Reason=status_reason or f"See the details in CloudWatch: {self.__context.log_stream_name}.",
            PhysicalResourceId=resource_id or self.__invocation_event.get("PhysicalResourceId") or self.__context.log_stream_name,
            StackId=self.__invocation_event["StackId"],
            RequestId=self.__invocation_event["RequestId"],
            LogicalResourceId=self.__invocation_event["LogicalResourceId"],
            NoEcho=False,
            Data=data or {},
        )

        response_json = json.dumps(response_body, default=lambda o: "<not serializable>")
        response_url = self.__invocation_event["ResponseURL"]
        self.__send(response_url, response_json)

    @staticmethod
    def __send(url: str, message: str) -> None:
        """
        Sends a json message to a specified url.

        :param url: A destination for the message.
        :param message: Message payload.

        :return: No return.
        """
        import urllib3

        http = urllib3.PoolManager()

        try:
            logging.info(f"Callback data: {message}.")
            r = http.request("PUT", url, body=message, headers={"Content-Type": "application/json"})
            logging.info(f"Status code: {str(r.data)}.")
        except Exception as e:
            logging.exception(f"Callback PUT failed: {repr(e)}.")
