"""Regression coverage for latest-run replay after ``kickoff_for_each``."""

from collections.abc import Generator
import gc
from unittest.mock import patch

from crewai.agent import Agent
from crewai.crew import Crew
from crewai.task import Task
from crewai.tasks.output_format import OutputFormat
from crewai.tasks.task_output import TaskOutput
import pytest

from tests.utils import wait_for_event_handlers


# Windows implements ``socket.socketpair`` with a loopback TCP connection.
# Permit only loopback so CrewAI can create its internal event loop while the
# repository-level network guard continues to block model and service calls.
pytestmark = pytest.mark.block_network(allowed_hosts=[r"127\.0\.0\.1\Z", r"::1\Z"])


@pytest.fixture(autouse=True)
def _drain_event_handlers_before_storage_cleanup(
    setup_test_environment: None,
) -> Generator[None, None, None]:
    yield
    wait_for_event_handlers()
    gc.collect()


def _crew() -> Crew:
    agent = Agent(
        role="Researcher",
        goal="Report on the requested topic.",
        backstory="A deterministic test agent.",
        allow_delegation=False,
    )
    task = Task(
        description="Report on {topic}",
        expected_output="A report on {topic}",
        agent=agent,
    )
    return Crew(agents=[agent], tasks=[task])


def _task_output(task: Task, *_args: object, **_kwargs: object) -> TaskOutput:
    return TaskOutput(
        description=task.description,
        raw=task.description,
        agent=task.agent.role if task.agent else "None",
        summary=task.description,
        output_format=OutputFormat.RAW,
        messages=[],
    )


def test_regular_kickoff_persists_and_replays_latest_run() -> None:
    crew = _crew()

    with patch.object(Task, "execute_sync", autospec=True, side_effect=_task_output):
        result = crew.kickoff(inputs={"topic": "control"})
        stored = crew._task_output_handler.load()
        assert stored is not None
        assert len(stored) == 1
        assert stored[0]["inputs"] == {"topic": "control"}
        replayed = crew.replay(stored[0]["task_id"])

    assert result.raw == "Report on control"
    assert replayed.raw == "Report on control"


def test_kickoff_for_each_persists_only_the_most_recent_run_for_replay() -> None:
    crew = _crew()

    with patch.object(
        Task, "execute_sync", autospec=True, side_effect=_task_output
    ) as execute_sync:
        results = crew.kickoff_for_each(
            inputs=[{"topic": "first"}, {"topic": "latest"}]
        )
        stored = crew._task_output_handler.load()
        assert stored is not None
        assert len(stored) == 1
        assert stored[0]["inputs"] == {"topic": "latest"}
        replayed = crew.replay(stored[0]["task_id"])
        replayed_stored = crew._task_output_handler.load()

    assert [result.raw for result in results] == [
        "Report on first",
        "Report on latest",
    ]
    assert replayed.raw == "Report on latest"
    assert execute_sync.call_count == 3
    assert execute_sync.call_args_list[-1].args[0].description == "Report on latest"
    assert replayed_stored is not None
    assert len(replayed_stored) == 1
    assert replayed_stored[0]["inputs"] == {"topic": "latest"}
    assert replayed_stored[0]["was_replayed"]
