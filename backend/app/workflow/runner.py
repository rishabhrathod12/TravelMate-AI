"""Starting, resuming and reading planning runs (ARCHITECTURE §8).

A run has an owner. Another person's run, a missing one and one that has ended are all "not found",
so a run id alone is never enough (SECURITY §2). Resuming needs the run to be waiting for a person.

Runs and their checkpoints live in memory and are lost on restart; durable storage is M9. The
limits (steps, tool calls, answers) come from the caller and end a run as `stopped_limit`.
"""

import os
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from app.domain.run import RunStatus
from app.llm.drafter import ItineraryDrafter
from app.tools.research import ResearchTools
from app.workflow.graph import CLARIFICATION, SELECTION, WorkflowDeps, build_graph
from app.workflow.limits import RunLimitExceeded, ToolBudget
from app.workflow.serde import new_checkpointer
from app.workflow.state import PlanningState, RunError, RunInput, RunLimits, RunOutcome
from app.workflow.tracing import refuse_third_party_tracing


class RunNotFound(Exception):
    """No such run for this owner (missing, someone else's, or never started)."""


class RunNotWaiting(Exception):
    """The run is not waiting for an answer, so there is nothing to resume."""


@dataclass
class _Run:
    owner: str
    budget: ToolBudget
    status: RunStatus
    limit_reason: str | None = None


class PlanningWorkflow:
    def __init__(
        self,
        tools: ResearchTools,
        drafter: ItineraryDrafter,
        limits: RunLimits,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        refuse_third_party_tracing(os.environ if environment is None else environment)
        self._limits = limits
        self._tools = tools
        self._drafter = drafter
        self._runs: dict[str, _Run] = {}
        self._budgets: dict[str, ToolBudget] = {}
        self._lock = threading.Lock()
        self._graph = build_graph(
            WorkflowDeps(tools=tools, drafter=drafter, limits=limits),
            self._budgets,
            checkpointer if checkpointer is not None else new_checkpointer(),
        )

    # -- public ----------------------------------------------------------------------------

    def start(self, owner: str, run_input: RunInput) -> RunOutcome:
        if not owner.strip():
            raise ValueError("a run needs an owner")
        run_id = secrets.token_urlsafe(16)
        budget = ToolBudget(self._limits.max_tool_calls)
        with self._lock:
            self._runs[run_id] = _Run(owner, budget, RunStatus.RUNNING)
            self._budgets[run_id] = budget
        state = PlanningState(
            draft=run_input.draft, currency=run_input.currency, rooms=run_input.rooms
        )
        return self._drive(run_id, state)

    def resume(self, run_id: str, owner: str, answer: Mapping[str, object]) -> RunOutcome:
        run = self._owned(run_id, owner)
        if run.status not in (RunStatus.AWAITING_CLARIFICATION, RunStatus.AWAITING_SELECTION):
            raise RunNotWaiting("the run is not waiting for an answer")
        run.status = RunStatus.RUNNING
        # The answer travels in an envelope: LangGraph ignores an empty resume value, and "I choose
        # nothing" is a legitimate, empty answer.
        return self._drive(run_id, Command(resume={"answer": dict(answer)}))

    def status(self, run_id: str, owner: str) -> RunOutcome:
        run = self._owned(run_id, owner)
        return self._outcome(run_id, run, None)

    # -- internals -------------------------------------------------------------------------

    def _owned(self, run_id: str, owner: str) -> _Run:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None or run.owner != owner:
            raise RunNotFound("no such run")
        return run

    def _config(self, run_id: str) -> RunnableConfig:
        return {
            "configurable": {"thread_id": run_id},
            "recursion_limit": self._limits.max_steps,
        }

    def _drive(self, run_id: str, graph_input: PlanningState | Command[Any]) -> RunOutcome:
        run = self._runs[run_id]
        config = self._config(run_id)
        interrupted: dict[str, object] | None = None
        try:
            result = self._graph.invoke(graph_input, config)
        except RunLimitExceeded as error:
            run.status = RunStatus.STOPPED_LIMIT
            run.limit_reason = str(error)
        except GraphRecursionError:
            run.status = RunStatus.STOPPED_LIMIT
            run.limit_reason = f"the run reached its limit of {self._limits.max_steps} steps"
        except Exception:
            run.status = RunStatus.FAILED
            raise
        else:
            pending = result.get("__interrupt__") if isinstance(result, dict) else None
            if pending:
                value = pending[0].value
                interrupted = dict(value) if isinstance(value, dict) else {}
                run.status = (
                    RunStatus.AWAITING_CLARIFICATION
                    if interrupted.get("kind") == CLARIFICATION
                    else RunStatus.AWAITING_SELECTION
                )
            else:
                state = PlanningState.model_validate(result)
                failed = any(error.fatal for error in state.errors)
                run.status = RunStatus.FAILED if failed else RunStatus.COMPLETED
        return self._outcome(run_id, run, interrupted)

    def _outcome(self, run_id: str, run: _Run, waiting_for: dict[str, object] | None) -> RunOutcome:
        snapshot = self._graph.get_state(self._config(run_id))
        values: Any = snapshot.values
        state = PlanningState.model_validate(values) if values else None
        errors: tuple[RunError, ...] = state.errors if state is not None else ()
        if waiting_for is None and run.status in (
            RunStatus.AWAITING_CLARIFICATION,
            RunStatus.AWAITING_SELECTION,
        ):
            waiting_for = self._pending(snapshot)
        return RunOutcome(
            run_id=run_id,
            status=run.status,
            waiting_for=waiting_for,
            summary=state.summary if state is not None else None,
            errors=errors,
            provider_calls=run.budget.used,
            llm_calls=state.llm_calls if state is not None else 0,
            limit_reason=run.limit_reason,
        )

    @staticmethod
    def _pending(snapshot: Any) -> dict[str, object] | None:
        for task in snapshot.tasks:
            for pending in task.interrupts:
                value = pending.value
                return dict(value) if isinstance(value, dict) else None
        return None


__all__ = ["PlanningWorkflow", "RunNotFound", "RunNotWaiting", "SELECTION"]
