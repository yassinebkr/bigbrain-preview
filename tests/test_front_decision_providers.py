"""Offline transport checks for the shared native front decision contract."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from bigbrain.front.decision import FrontDecision, FRONT_TOOL_SCHEMA


ANSWER=json.dumps({"decision":{"operation":"respond","reply":"Bonjour"}})


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True,False])
async def test_litellm_forces_one_native_decision_and_rejects_text_fallback(valid):
    from bigbrain.llm.litellm_provider import LiteLLMProvider
    provider=object.__new__(LiteLLMProvider)
    provider.default_model="fixture-model"
    tool=SimpleNamespace(function=SimpleNamespace(name="bigbrain_front_decision",arguments=ANSWER))
    choice=SimpleNamespace(finish_reason="tool_calls",message=SimpleNamespace(tool_calls=[tool] if valid else [],content="Je relance"))
    completion=AsyncMock(return_value=SimpleNamespace(choices=[choice]))
    provider._litellm=SimpleNamespace(acompletion=completion)
    request=provider.chat_complete([{"role":"user","content":"Bonjour"}],tool_schema=FRONT_TOOL_SCHEMA)
    if valid:
        assert FrontDecision.model_validate_json(await request).decision.reply=="Bonjour"
    else:
        with pytest.raises(ValueError,match="exactly"):
            await request
    kwargs=completion.call_args.kwargs
    assert kwargs["stream"] is False and kwargs["parallel_tool_calls"] is False
    assert kwargs["tool_choice"]["function"]["name"]=="bigbrain_front_decision"
    assert "tool_schema" not in kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True,False])
async def test_anthropic_forces_native_decision_and_preserves_all_system_context(valid):
    from bigbrain.llm.anthropic_oauth import AnthropicOAuthProvider
    provider=object.__new__(AnthropicOAuthProvider)
    provider.default_model="fixture-model"
    provider._headers={}
    def respond(request):
        body=json.loads(request.content)
        assert body["tool_choice"]["type"]=="tool"
        assert body["tools"][0]["input_schema"]==FRONT_TOOL_SCHEMA["parameters"]
        system=json.dumps(body["system"])
        assert "first instruction" in system and "second instruction" in system
        content=[{"type":"tool_use","name":"bigbrain_front_decision","input":json.loads(ANSWER)}] if valid else [{"type":"text","text":"Je relance"}]
        return httpx.Response(200,json={"stop_reason":"tool_use","content":content})
    provider._client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        call=provider.chat_complete([{"role":"system","content":"first instruction"},
            {"role":"system","content":"second instruction"},{"role":"user","content":"Bonjour"}],tool_schema=FRONT_TOOL_SCHEMA)
        if valid:
            assert FrontDecision.model_validate_json(await call).decision.reply=="Bonjour"
        else:
            with pytest.raises(ValueError,match="exactly"):
                await call
    finally:
        await provider._client.aclose()


@pytest.mark.asyncio
async def test_codex_receives_closed_native_output_schema_without_launching_session():
    from bigbrain.llm.codex_provider import CodexProvider
    provider=object.__new__(CodexProvider)
    provider.run_turn=AsyncMock(return_value=(ANSWER,None))
    result=await provider.chat_complete([{"role":"user","content":"Bonjour"}],tool_schema=FRONT_TOOL_SCHEMA)
    assert FrontDecision.model_validate_json(result).decision.reply=="Bonjour"
    assert provider.run_turn.call_args.kwargs["output_schema"]["additionalProperties"] is False
