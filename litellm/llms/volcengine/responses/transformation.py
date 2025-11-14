from typing import TYPE_CHECKING, Any

from litellm.llms.openai.responses.transformation import OpenAIResponsesAPIConfig
from litellm.types.utils import LlmProviders


if TYPE_CHECKING:
    from litellm.litellm_core_utils.litellm_logging import Logging as _LiteLLMLoggingObj

    LiteLLMLoggingObj = _LiteLLMLoggingObj
else:
    LiteLLMLoggingObj = Any


class VolcEngineResponsesAPIConfig(OpenAIResponsesAPIConfig):
    @property
    def custom_llm_provider(self) -> LlmProviders:
        return LlmProviders.VOLCENGINE
