"""Shared test doubles for coordinator-level tests (Phase 5).

``capturing_model`` builds a PydanticAI ``FunctionModel`` that returns a fixed
``RoutingDecision`` *and records every user prompt the coordinator sent it*.
PydanticAI's ``TestModel(custom_output_args=...)`` can fix the output but can't
show what input reached the model — and Phase 5's central claim ("the rendered
conversation context actually reaches the classifier, and stateless prompts are
unchanged") is precisely a claim about the input.
"""

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.models import RoutingDecision


def capturing_model(decision: RoutingDecision, seen_prompts: list[str]) -> FunctionModel:
    """Return a fake model answering ``decision`` and appending each user
    prompt it receives to ``seen_prompts`` (mutated in place).

    Inputs: the fixed decision to return; a list the caller owns and inspects.
    Output: a ``FunctionModel`` usable as ``build_coordinator_agent(model=...)``.
    """

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, UserPromptPart):
                    seen_prompts.append(part.content)
        output_tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(output_tool.name, decision.model_dump(mode="json"))])

    return FunctionModel(respond)
