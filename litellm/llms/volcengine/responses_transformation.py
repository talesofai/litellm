from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Union

import httpx

import litellm
from litellm._logging import verbose_logger
from litellm.llms.openai.responses.transformation import OpenAIResponsesAPIConfig
from litellm.litellm_core_utils.core_helpers import process_response_headers
from litellm.litellm_core_utils.llm_response_utils.convert_dict_to_response import (
    _safe_convert_created_field,
)
from litellm.secret_managers.main import get_secret_str
from litellm.types.llms.openai import (
    ResponsesAPIOptionalRequestParams,
    ResponsesAPIResponse,
)
from litellm.types.responses.main import DeleteResponseResult
from litellm.types.router import GenericLiteLLMParams
from litellm.types.utils import LlmProviders

from .common_utils import (
    VolcEngineError,
    get_volcengine_base_url,
    get_volcengine_headers,
)

if TYPE_CHECKING:
    from litellm.litellm_core_utils.litellm_logging import Logging as _LiteLLMLoggingObj

    LiteLLMLoggingObj = _LiteLLMLoggingObj
else:
    LiteLLMLoggingObj = Any


class VolcEngineResponsesAPIConfig(OpenAIResponsesAPIConfig):
    _SUPPORTED_OPTIONAL_PARAMS: List[str] = [
        # Doc-listed knobs
        "instructions",
        "max_output_tokens",
        "previous_response_id",
        "store",
        "reasoning",
        "stream",
        "temperature",
        "top_p",
        "text",
        "tools",
        "tool_choice",
        "max_tool_calls",
        # Request plumbing helpers
        "extra_headers",
        "extra_query",
        "extra_body",
        "timeout",
    ]

    @property
    def custom_llm_provider(self) -> LlmProviders:
        return LlmProviders.VOLCENGINE

    def get_supported_openai_params(self, model: str) -> list:
        """
        Volcengine Responses API: only documented parameters are supported.
        """
        return ["input", "model"] + list(self._SUPPORTED_OPTIONAL_PARAMS)

    def get_error_class(
        self, error_message: str, status_code: int, headers: Union[dict, httpx.Headers]
    ):
        return VolcEngineError(
            status_code=status_code,
            message=error_message,
            headers=headers,
        )

    def validate_environment(
        self, headers: dict, model: str, litellm_params: Optional[GenericLiteLLMParams]
    ) -> dict:
        """
        Build auth headers for Volcengine Responses API.
        """
        if litellm_params is None:
            litellm_params = GenericLiteLLMParams()
        elif isinstance(litellm_params, dict):
            litellm_params = GenericLiteLLMParams(**litellm_params)

        api_key = (
            litellm_params.api_key
            or litellm.api_key
            or get_secret_str("ARK_API_KEY")
            or get_secret_str("VOLCENGINE_API_KEY")
        )

        if api_key is None:
            raise ValueError(
                "Volcengine API key is required. Set ARK_API_KEY / VOLCENGINE_API_KEY or pass api_key."
            )

        return get_volcengine_headers(api_key=api_key, extra_headers=headers)

    def get_complete_url(
        self,
        api_base: Optional[str],
        litellm_params: dict,
    ) -> str:
        """
        Construct Volcengine Responses API endpoint.
        """
        base_url = (
            api_base
            or litellm.api_base
            or get_secret_str("VOLCENGINE_API_BASE")
            or get_secret_str("ARK_API_BASE")
            or get_volcengine_base_url()
        )

        base_url = base_url.rstrip("/")

        if base_url.endswith("/responses"):
            return base_url
        if base_url.endswith("/api/v3"):
            return f"{base_url}/responses"
        return f"{base_url}/api/v3/responses"

    def map_openai_params(
        self,
        response_api_optional_params: ResponsesAPIOptionalRequestParams,
        model: str,
        drop_params: bool,
    ) -> Dict:
        """
        Volcengine Responses API aligns with OpenAI parameters.
        Remove parameters not supported by the public docs.
        """
        params = {
            key: value
            for key, value in dict(response_api_optional_params).items()
            if key in self._SUPPORTED_OPTIONAL_PARAMS
        }

        # Volcengine docs do not list parallel_tool_calls; drop it to avoid backend errors.
        if "parallel_tool_calls" in params:
            verbose_logger.debug(
                "Volcengine Responses API: dropping unsupported 'parallel_tool_calls' param."
            )
            params.pop("parallel_tool_calls", None)

        return params

    def transform_response_api_response(
        self,
        model: str,
        raw_response: httpx.Response,
        logging_obj: LiteLLMLoggingObj,
    ) -> ResponsesAPIResponse:
        try:
            logging_obj.post_call(
                original_response=raw_response.text,
                additional_args={"complete_input_dict": {}},
            )
            raw_response_json = raw_response.json()
            if "created_at" in raw_response_json:
                raw_response_json["created_at"] = _safe_convert_created_field(
                    raw_response_json["created_at"]
                )
        except Exception:
            raise VolcEngineError(
                message=raw_response.text, status_code=raw_response.status_code
            )

        raw_response_headers = dict(raw_response.headers)
        processed_headers = process_response_headers(raw_response_headers)

        try:
            response = ResponsesAPIResponse(**raw_response_json)
        except Exception:
            verbose_logger.debug(
                "Volcengine Responses API: falling back to model_construct for response parsing."
            )
            response = ResponsesAPIResponse.model_construct(**raw_response_json)

        response._hidden_params["additional_headers"] = processed_headers
        response._hidden_params["headers"] = raw_response_headers
        return response

    #########################################################
    ########## DELETE RESPONSE API TRANSFORMATION ##############
    #########################################################
    def transform_delete_response_api_request(
        self,
        response_id: str,
        api_base: str,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> Tuple[str, Dict]:
        url = f"{api_base}/{response_id}"
        data: Dict = {}
        return url, data

    def transform_delete_response_api_response(
        self,
        raw_response: httpx.Response,
        logging_obj: LiteLLMLoggingObj,
    ) -> DeleteResponseResult:
        try:
            raw_response_json = raw_response.json()
        except Exception:
            raise VolcEngineError(
                message=raw_response.text, status_code=raw_response.status_code
            )
        try:
            return DeleteResponseResult(**raw_response_json)
        except Exception:
            verbose_logger.debug(
                "Volcengine Responses API: falling back to model_construct for delete response parsing."
            )
            return DeleteResponseResult.model_construct(**raw_response_json)

    #########################################################
    ########## GET RESPONSE API TRANSFORMATION ###############
    #########################################################
    def transform_get_response_api_request(
        self,
        response_id: str,
        api_base: str,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> Tuple[str, Dict]:
        url = f"{api_base}/{response_id}"
        data: Dict = {}
        return url, data

    def transform_get_response_api_response(
        self,
        raw_response: httpx.Response,
        logging_obj: LiteLLMLoggingObj,
    ) -> ResponsesAPIResponse:
        try:
            raw_response_json = raw_response.json()
        except Exception:
            raise VolcEngineError(
                message=raw_response.text, status_code=raw_response.status_code
            )

        raw_response_headers = dict(raw_response.headers)
        processed_headers = process_response_headers(raw_response_headers)

        response = ResponsesAPIResponse(**raw_response_json)
        response._hidden_params["additional_headers"] = processed_headers
        response._hidden_params["headers"] = raw_response_headers
        return response

    #########################################################
    ########## LIST INPUT ITEMS TRANSFORMATION #############
    #########################################################
    def transform_list_input_items_request(
        self,
        response_id: str,
        api_base: str,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
        after: Optional[str] = None,
        before: Optional[str] = None,
        include: Optional[List[str]] = None,
        limit: int = 20,
        order: Literal["asc", "desc"] = "desc",
    ) -> Tuple[str, Dict]:
        url = f"{api_base}/{response_id}/input_items"
        params: Dict[str, Any] = {}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        if include:
            params["include"] = ",".join(include)
        if limit is not None:
            params["limit"] = limit
        if order is not None:
            params["order"] = order
        return url, params

    def transform_list_input_items_response(
        self,
        raw_response: httpx.Response,
        logging_obj: LiteLLMLoggingObj,
    ) -> Dict:
        try:
            return raw_response.json()
        except Exception:
            raise VolcEngineError(
                message=raw_response.text, status_code=raw_response.status_code
            )

    #########################################################
    ########## CANCEL RESPONSE API TRANSFORMATION ##########
    #########################################################
    def transform_cancel_response_api_request(
        self,
        response_id: str,
        api_base: str,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> Tuple[str, Dict]:
        url = f"{api_base}/{response_id}/cancel"
        data: Dict = {}
        return url, data

    def transform_cancel_response_api_response(
        self,
        raw_response: httpx.Response,
        logging_obj: LiteLLMLoggingObj,
    ) -> ResponsesAPIResponse:
        try:
            raw_response_json = raw_response.json()
        except Exception:
            raise VolcEngineError(
                message=raw_response.text, status_code=raw_response.status_code
            )

        raw_response_headers = dict(raw_response.headers)
        processed_headers = process_response_headers(raw_response_headers)

        response = ResponsesAPIResponse(**raw_response_json)
        response._hidden_params["additional_headers"] = processed_headers
        response._hidden_params["headers"] = raw_response_headers
        return response
