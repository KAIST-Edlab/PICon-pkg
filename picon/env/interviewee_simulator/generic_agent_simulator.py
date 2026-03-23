from litellm.cost_calculator import completion_cost
from picon.utils import get_completion
from picon.schemas import IntervieweeResponse
from picon.env.interviewee_simulator.base_interviewee_simulator import BaseIntervieweeSimulator
import logging


class GenericAgentSimulator(BaseIntervieweeSimulator):
    """
    Universal interviewee simulator that works with any OpenAI-compatible API endpoint.

    All evaluation targets — whether cloud LLM APIs, self-hosted vLLM, or custom
    wrapping servers — are accessed through the same /v1/chat/completions interface.

    Required kwargs:
        - model (str): Model name at the endpoint.
        - persona (str): System prompt / persona description.
                         Can be empty if the server manages persona internally (e.g., wrapping servers).

    Optional kwargs:
        - api_base (str): API endpoint URL. None = litellm default routing.
        - api_key (str): API key. Defaults to "no-key".
        - name (str): Interviewee name. Defaults to "GenericAgent".
        - user_message_template (str): Format string for user messages.
            Defaults to "{message}" (no wrapping).
            Examples: "user request: {message}", "### QUESTION ###\\n{message}\\n\\n### YOUR RESPONSE ###"
        - completion_kwargs (dict): Extra kwargs for get_completion (temperature, top_p, max_tokens, etc.)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        assert 'model' in kwargs, "GenericAgentSimulator requires 'model'"

        self.name = kwargs.get('name', 'GenericAgent')
        self.user_message_template = kwargs.get('user_message_template', '{message}')
        self.extra_completion_kwargs = kwargs.get('completion_kwargs', {})

        # Build api_base: explicit > host+port > None (litellm default)
        self.api_base = kwargs.get('api_base')
        if not self.api_base:
            host = kwargs.get('simulator_host')
            port = kwargs.get('port')
            if host and port:
                self.api_base = f"http://{host}:{port}/v1"

        self.api_key = kwargs.get('api_key', 'no-key')

        # When api_base is set and model has no provider prefix, add "openai/"
        # so litellm routes to the OpenAI-compatible endpoint
        model = kwargs['model']
        if self.api_base and '/' not in model:
            model = f"openai/{model}"
        self.client_or_model = model

        # Initialize chat history
        persona = kwargs.get('persona', '')
        self.history = [{"role": "system", "content": persona}] if persona else []

        # Determine max tokens for truncation
        try:
            self.max_tokens = self.get_max_token()
        except Exception:
            logging.warning(f"Could not determine max tokens for {self.client_or_model}. Using default 8192.")
            self.max_tokens = 8192

    def _get_response(self, message: str) -> IntervieweeResponse:
        formatted = self.user_message_template.format(message=message)
        self.history.append({"role": "user", "content": formatted})
        self._truncate_history()

        call_kwargs = {
            "model": self.client_or_model,
            "messages": self.history,
            "reasoning_effort": "low",
        }
        if self.api_base:
            call_kwargs["api_base"] = self.api_base
        if self.api_key and self.api_key != "no-key":
            call_kwargs["api_key"] = self.api_key
        call_kwargs.update(self.extra_completion_kwargs)

        res = get_completion(**call_kwargs)

        try:
            self.cost += completion_cost(completion_response=res)
        except Exception:
            pass

        response = res.choices[0].message.content.strip()
        self.history.append({"role": "assistant", "content": response})

        self._ai_check(message, response)

        return IntervieweeResponse(question=message, content=response)
