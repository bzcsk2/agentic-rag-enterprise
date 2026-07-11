from __future__ import annotations

from typing import Any, Callable, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator


class UnsupportedProviderError(LookupError):
    """Raised when create_provider is called with a provider that has no implementation."""


class StructuredResponseTypeError(TypeError):
    """Raised when a registered structured response does not match the expected schema."""


class MissingFakeResponseError(LookupError):
    """Raised when FakeModel.invoke_structured has no registered response for the input."""


@runtime_checkable
class StructuredProvider(Protocol):
    """Callable that returns a Pydantic model from a message list."""

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> BaseModel: ...


@runtime_checkable
class ModelProvider(Protocol):
    """Minimal interface for a model provider in this project.

    Real providers (Ollama, OpenAI, etc.) implement this protocol so that
    agents and graph nodes can be tested with FakeModel and run with real
    models without changing their call sites.
    """

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...

    def with_structured_output(
        self, schema: type[BaseModel], **kwargs: Any
    ) -> StructuredProvider: ...


class ModelCapabilities(BaseModel):
    native_tool_calling: bool = False
    parallel_tool_calls: bool = False
    structured_output: bool = True
    strict_json_schema: bool = False
    max_context_tokens: int = 8192
    max_output_tokens: int | None = None
    supports_streaming: bool = False
    supports_usage_reporting: bool = False
    supports_seed: bool = False
    supports_temperature: bool = False

    @field_validator("max_context_tokens")
    @classmethod
    def _positive_context(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_context_tokens must be > 0")
        return v

    @field_validator("max_output_tokens")
    @classmethod
    def _positive_output(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("max_output_tokens must be > 0 when set")
        return v


class ModelProfile(BaseModel):
    provider: str
    model: str
    purpose: Literal[
        "orchestrator",
        "planner",
        "judge",
        "synthesis",
        "embedding",
        "reranker",
    ]
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    timeout_seconds: float = 30.0
    max_retries: int = 2

    @field_validator("timeout_seconds")
    @classmethod
    def _positive_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("timeout_seconds must be > 0")
        return v

    @field_validator("max_retries")
    @classmethod
    def _nonnegative_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be >= 0")
        return v


class ModelInvocation(BaseModel):
    invocation_id: str = ""
    messages: list[dict[str, str]] = Field(default_factory=list)
    profile: ModelProfile | None = None
    structured_schema: str = ""
    output: Any = None
    duration_ms: float = 0.0


class _StructuredWrapper:
    """Wrapper returned by with_structured_output().

    Delegates to FakeModel.invoke_structured() and fulfills the project's
    StructuredProvider protocol.
    """

    def __init__(self, model: FakeModel, schema: type[BaseModel]) -> None:
        self._model = model
        self._schema = schema

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> BaseModel:
        return self._model.invoke_structured(messages, self._schema, **kwargs)


class FakeModel:
    """Deterministic fake model for testing and development.

    Implements the project's ModelProvider protocol. Tests register
    predefined responses for specific input patterns; unregistered inputs
    raise MissingFakeResponseError for structured calls or return a
    configurable default text for plain-text calls.
    """

    def __init__(self, profile: ModelProfile | None = None) -> None:
        self.profile = profile or ModelProfile(
            provider="fake",
            model="fake-model",
            purpose="orchestrator",
        )
        if self.profile.provider != "fake":
            raise UnsupportedProviderError(
                f"FakeModel requires provider='fake', got {self.profile.provider!r}. "
                f"Use create_provider() for provider dispatch."
            )
        self._invocations: list[ModelInvocation] = []
        self._id_counter: int = 0
        self._text_responses: dict[str, str] = {}
        self._structured_responses: dict[str, BaseModel] = {}
        self._default_text: str = "Fake model response."
        self._structured_factories: dict[type[BaseModel], Callable[[], BaseModel]] = {}

    def register_text(self, input_pattern: str, response: str) -> None:
        self._text_responses[input_pattern] = response

    def register_structured(self, input_pattern: str, response: BaseModel) -> None:
        self._structured_responses[input_pattern] = response

    def set_default_text(self, text: str) -> None:
        self._default_text = text

    def register_structured_factory(
        self, schema: type[BaseModel], factory: Callable[[], BaseModel]
    ) -> None:
        self._structured_factories[schema] = factory

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        inp = self._match_key(messages)
        output = self._text_responses.get(inp, self._default_text)
        inv = ModelInvocation(
            invocation_id=self._next_id(),
            messages=messages,
            profile=self.profile,
            output=output,
        )
        self._invocations.append(inv)
        return output

    def invoke_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        inp = self._match_key(messages)
        registered = self._structured_responses.get(inp)
        if registered is not None:
            if type(registered) is not schema:
                raise StructuredResponseTypeError(
                    f"Registered response for input {inp!r} is "
                    f"{type(registered).__name__}, expected {schema.__name__}"
                )
            output = registered
        elif schema in self._structured_factories:
            output = self._structured_factories[schema]()
            if type(output) is not schema:
                raise StructuredResponseTypeError(
                    f"Structured factory for {schema.__name__} returned "
                    f"{type(output).__name__}, expected {schema.__name__}"
                )
        else:
            raise MissingFakeResponseError(
                f"No structured response registered for input {inp!r} "
                f"and no default factory for {schema.__name__}. "
                "Use register_structured(pattern, response) or "
                "register_structured_factory(schema, factory)."
            )
        inv = ModelInvocation(
            invocation_id=self._next_id(),
            messages=messages,
            profile=self.profile,
            structured_schema=schema.__name__,
            output=output.model_dump(),
        )
        self._invocations.append(inv)
        return output

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> _StructuredWrapper:
        return _StructuredWrapper(self, schema)

    @property
    def invocations(self) -> list[ModelInvocation]:
        return list(self._invocations)

    def reset(self) -> None:
        self._invocations.clear()
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"fake-{self._id_counter:06d}"

    @staticmethod
    def _match_key(messages: list[dict[str, str]]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return str(messages[-1]["content"]) if messages else ""


SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"fake"})


def create_provider(profile: ModelProfile) -> FakeModel:
    """Create a model provider for the given profile.

    Currently only "fake" is implemented. Real provider dispatch (Ollama,
    OpenAI, etc.) will be added in the corresponding capability Issue.
    """
    if profile.provider not in SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Provider {profile.provider!r} is not yet supported. "
            f"Supported providers: {sorted(SUPPORTED_PROVIDERS)}. "
            f"Use provider='fake' for testing and development."
        )
    return FakeModel(profile)
