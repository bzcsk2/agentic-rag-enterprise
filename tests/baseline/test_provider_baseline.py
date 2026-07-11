"""Baseline characterization tests for provider profiles and Fake Model contract.

Covers ModelCapabilities, ModelProfile, FakeModel (invoke, structured output,
invocation recording, deterministic IDs), error contracts (UnsupportedProviderError,
MissingFakeResponseError, StructuredResponseTypeError), and boundary validation.
"""

import pytest

from agentic_rag_enterprise.providers import (
    FakeModel,
    MissingFakeResponseError,
    ModelCapabilities,
    ModelProfile,
    StructuredResponseTypeError,
    UnsupportedProviderError,
    create_provider,
)
from agentic_rag_enterprise.schemas import QueryPlan


# =============================================================================
# ModelCapabilities
# =============================================================================


def test_capabilities_defaults() -> None:
    caps = ModelCapabilities()
    assert caps.structured_output is True
    assert caps.native_tool_calling is False
    assert caps.max_context_tokens == 8192


def test_capabilities_custom_values() -> None:
    caps = ModelCapabilities(
        native_tool_calling=True,
        max_context_tokens=4096,
        supports_streaming=True,
    )
    assert caps.native_tool_calling is True
    assert caps.max_context_tokens == 4096
    assert caps.supports_streaming is True
    assert caps.structured_output is True


def test_capabilities_rejects_zero_context() -> None:
    with pytest.raises(ValueError, match="max_context_tokens must be > 0"):
        ModelCapabilities(max_context_tokens=0)


def test_capabilities_rejects_negative_context() -> None:
    with pytest.raises(ValueError, match="max_context_tokens must be > 0"):
        ModelCapabilities(max_context_tokens=-1)


def test_capabilities_rejects_zero_output_tokens() -> None:
    with pytest.raises(ValueError, match="max_output_tokens must be > 0"):
        ModelCapabilities(max_output_tokens=0)


def test_capabilities_accepts_none_output_tokens() -> None:
    caps = ModelCapabilities(max_output_tokens=None)
    assert caps.max_output_tokens is None


# =============================================================================
# ModelProfile
# =============================================================================


def test_profile_all_purposes() -> None:
    for purpose in ("orchestrator", "planner", "judge", "synthesis", "embedding", "reranker"):
        profile = ModelProfile(provider="ollama", model="m", purpose=purpose)  # type: ignore[arg-type]
        assert profile.purpose == purpose


def test_profile_defaults() -> None:
    profile = ModelProfile(provider="ollama", model="granite4.1:8b", purpose="planner")
    assert profile.capabilities.structured_output is True
    assert profile.timeout_seconds == 30.0
    assert profile.max_retries == 2


def test_profile_with_capabilities() -> None:
    caps = ModelCapabilities(native_tool_calling=True, max_context_tokens=16384)
    profile = ModelProfile(
        provider="openai",
        model="gpt-4o",
        purpose="orchestrator",
        capabilities=caps,
        timeout_seconds=60.0,
    )
    assert profile.capabilities.native_tool_calling is True
    assert profile.timeout_seconds == 60.0


def test_profile_rejects_zero_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
        ModelProfile(provider="fake", model="m", purpose="planner", timeout_seconds=0)


def test_profile_rejects_negative_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
        ModelProfile(provider="fake", model="m", purpose="planner", timeout_seconds=-1)


def test_profile_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        ModelProfile(provider="fake", model="m", purpose="planner", max_retries=-1)


def test_profile_accepts_zero_retries() -> None:
    profile = ModelProfile(provider="fake", model="m", purpose="planner", max_retries=0)
    assert profile.max_retries == 0


# =============================================================================
# create_provider
# =============================================================================


def test_create_provider_fake_success() -> None:
    profile = ModelProfile(provider="fake", model="fake-model", purpose="orchestrator")
    model = create_provider(profile)
    assert isinstance(model, FakeModel)
    assert model.profile.provider == "fake"


def test_create_provider_ollama_raises() -> None:
    profile = ModelProfile(provider="ollama", model="granite4.1:8b", purpose="planner")
    with pytest.raises(UnsupportedProviderError, match="ollama"):
        create_provider(profile)


def test_create_provider_openai_raises() -> None:
    profile = ModelProfile(provider="openai", model="gpt-4o", purpose="orchestrator")
    with pytest.raises(UnsupportedProviderError, match="openai"):
        create_provider(profile)


def test_create_provider_unknown_raises() -> None:
    profile = ModelProfile(provider="nonexistent", model="x", purpose="embedding")
    with pytest.raises(UnsupportedProviderError, match="nonexistent"):
        create_provider(profile)


# =============================================================================
# FakeModel: invoke (plain text)
# =============================================================================


def test_fake_invoke_returns_default() -> None:
    model = FakeModel()
    result = model.invoke([{"role": "user", "content": "hello"}])
    assert result == "Fake model response."


def test_fake_invoke_custom_default_text() -> None:
    model = FakeModel()
    model.set_default_text("custom default")
    result = model.invoke([{"role": "user", "content": "hello"}])
    assert result == "custom default"


def test_fake_invoke_registered_response() -> None:
    model = FakeModel()
    model.register_text("hello", "Hi there!")
    result = model.invoke([{"role": "user", "content": "hello"}])
    assert result == "Hi there!"


def test_fake_invoke_messages() -> None:
    model = FakeModel()
    result = model.invoke(
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "test"},
        ]
    )
    assert result == "Fake model response."
    assert len(model.invocations) == 1
    inv = model.invocations[0]
    assert inv.messages[0]["role"] == "system"


# =============================================================================
# FakeModel: structured output
# =============================================================================


def test_fake_invoke_structured_unregistered_raises() -> None:
    model = FakeModel()
    with pytest.raises(MissingFakeResponseError, match="No structured response"):
        model.invoke_structured([{"role": "user", "content": "plan this"}], QueryPlan)


def test_fake_invoke_structured_registered_works() -> None:
    model = FakeModel()
    custom_plan = QueryPlan(task_type="multi_hop", required_facts=["fact1"])
    model.register_structured("plan this", custom_plan)
    result = model.invoke_structured(
        [{"role": "user", "content": "plan this"}],
        QueryPlan,
    )
    assert result.task_type == "multi_hop"
    assert result.required_facts == ["fact1"]


def test_fake_invoke_structured_wrong_type_raises() -> None:
    model = FakeModel()

    class WrongSchema(QueryPlan):
        pass

    model.register_structured("plan this", WrongSchema())
    with pytest.raises(StructuredResponseTypeError, match="WrongSchema"):
        model.invoke_structured(
            [{"role": "user", "content": "plan this"}],
            QueryPlan,
        )


def test_fake_invoke_structured_factory_works() -> None:
    model = FakeModel()
    model.register_structured_factory(QueryPlan, lambda: QueryPlan(task_type="factory_mode"))
    result = model.invoke_structured(
        [{"role": "user", "content": "anything"}],
        QueryPlan,
    )
    assert result.task_type == "factory_mode"


def test_fake_invoke_structured_factory_wrong_type_raises() -> None:
    model = FakeModel()

    class WrongSchema(QueryPlan):
        pass

    model.register_structured_factory(QueryPlan, lambda: WrongSchema(required_facts=["x"]))
    with pytest.raises(StructuredResponseTypeError, match="WrongSchema"):
        model.invoke_structured(
            [{"role": "user", "content": "anything"}],
            QueryPlan,
        )


def test_fake_with_structured_output_wrapper() -> None:
    model = FakeModel()
    custom_plan = QueryPlan(task_type="multi_hop", required_facts=["f1"])
    model.register_structured("test", custom_plan)
    structured = model.with_structured_output(QueryPlan)
    result = structured.invoke([{"role": "user", "content": "test"}])
    assert isinstance(result, QueryPlan)
    assert result.task_type == "multi_hop"


def test_fake_with_structured_output_unregistered_raises() -> None:
    model = FakeModel()
    structured = model.with_structured_output(QueryPlan)
    with pytest.raises(MissingFakeResponseError):
        structured.invoke([{"role": "user", "content": "anything"}])


# =============================================================================
# FakeModel: deterministic IDs and duration
# =============================================================================


def test_fake_invocation_ids_are_deterministic() -> None:
    model = FakeModel()
    model.invoke([{"role": "user", "content": "q1"}])
    model.invoke([{"role": "user", "content": "q2"}])
    assert model.invocations[0].invocation_id == "fake-000001"
    assert model.invocations[1].invocation_id == "fake-000002"


def test_fake_invocation_duration_zero() -> None:
    model = FakeModel()
    model.invoke([{"role": "user", "content": "x"}])
    assert model.invocations[0].duration_ms == 0.0


def test_fake_reset_resets_counter() -> None:
    model = FakeModel()
    model.invoke([{"role": "user", "content": "q1"}])
    model.reset()
    model.invoke([{"role": "user", "content": "q2"}])
    assert model.invocations[0].invocation_id == "fake-000001"


# =============================================================================
# FakeModel: invocation recording
# =============================================================================


def test_fake_records_invocations() -> None:
    model = FakeModel()
    model.invoke([{"role": "user", "content": "q1"}])
    model.invoke([{"role": "user", "content": "q2"}])
    assert len(model.invocations) == 2


def test_fake_invocation_has_profile_and_id() -> None:
    model = FakeModel()
    model.invoke([{"role": "user", "content": "x"}])
    inv = model.invocations[0]
    assert inv.profile is not None
    assert inv.profile.provider == "fake"
    assert inv.invocation_id == "fake-000001"


def test_fake_invocation_structured_schema_name() -> None:
    model = FakeModel()
    model.register_structured("x", QueryPlan())
    model.invoke_structured([{"role": "user", "content": "x"}], QueryPlan)
    inv = model.invocations[0]
    assert inv.structured_schema == "QueryPlan"
    assert isinstance(inv.output, dict)


def test_fake_reset_clears_invocations() -> None:
    model = FakeModel()
    model.invoke([{"role": "user", "content": "x"}])
    assert len(model.invocations) == 1
    model.reset()
    assert model.invocations == []


# =============================================================================
# FakeModel: profile integration
# =============================================================================


def test_fake_constructor_rejects_ollama() -> None:
    profile = ModelProfile(provider="ollama", model="m", purpose="planner")
    with pytest.raises(UnsupportedProviderError, match="ollama"):
        FakeModel(profile)


def test_fake_constructor_rejects_openai() -> None:
    profile = ModelProfile(provider="openai", model="gpt-4o", purpose="orchestrator")
    with pytest.raises(UnsupportedProviderError, match="openai"):
        FakeModel(profile)


def test_fake_with_custom_profile() -> None:
    profile = ModelProfile(
        provider="fake",
        model="custom-model",
        purpose="judge",
    )
    model = FakeModel(profile)
    assert model.profile.model == "custom-model"
    assert model.profile.purpose == "judge"


def test_fake_profile_in_invocation() -> None:
    profile = ModelProfile(provider="fake", model="fm", purpose="planner")
    model = FakeModel(profile)
    model.invoke([{"role": "user", "content": "test"}])
    assert model.invocations[0].profile is not None
    assert model.invocations[0].profile.provider == "fake"
