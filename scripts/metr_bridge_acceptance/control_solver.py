"""Deterministic no-provider solvers for the genuine METR bridge controls."""
from __future__ import annotations

import inspect_ai.model
import inspect_ai.solver
import inspect_ai.tool

MOCK_MODEL_LABEL = "NoProviderMockModel/no-paid-model"
SOLVER_EVENTS: dict[str, int] = {}


@inspect_ai.solver.solver
def fixed_count_odds_solver(control_name: str, answer: str | None) -> inspect_ai.solver.Solver:
    """A no-provider deterministic solver patterned on bridge tests.

    If `answer` is a string, emit a submit tool call carrying that answer.
    If `answer` is None, emit plain text without a submit tool call. The bridge scorer
    currently falls back to `state.output.completion`, so this is a no-submit-tool-call
    fallback-answer control, not proof that the bridge observed no answer.
    """

    async def solve(
        state: inspect_ai.solver.TaskState, generate: inspect_ai.solver.Generate
    ) -> inspect_ai.solver.TaskState:
        SOLVER_EVENTS[control_name] = SOLVER_EVENTS.get(control_name, 0) + 1
        if answer is None:
            state.output = inspect_ai.model.ModelOutput.from_content(
                model=MOCK_MODEL_LABEL,
                content="NO_SUBMISSION_CONTROL",
            )
            state.messages.append(state.output.message)
            return state

        tool_call = inspect_ai.tool.ToolCall(
            id=f"submit-{answer}",
            function="submit",
            arguments={"answer": answer},
        )
        state.output = inspect_ai.model.ModelOutput(
            model=MOCK_MODEL_LABEL,
            choices=[
                inspect_ai.model.ChatCompletionChoice(
                    message=inspect_ai.model.ChatMessageAssistant(
                        content=f"Calling tool {tool_call.function}",
                        model=MOCK_MODEL_LABEL,
                        source="generate",
                        tool_calls=[tool_call],
                    ),
                    stop_reason="tool_calls",
                )
            ],
        )
        state.messages.append(state.output.message)
        return state

    return solve
