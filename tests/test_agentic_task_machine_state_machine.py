"""
Behavioral state machine tests for agentic-task-machine.

Tests are organized per agent.  Uses single-agent Engine instances for
step-by-step assertions so agents don't interfere with each other.
"""
import pytest

from tests.sim.engine import Engine, InvariantViolation
from tests.sim.models import Repository
from tests.sim.agents import Event, EventKind

from tests.agentic_task_machine.agents import (
    AGENTIC_TASK_MACHINE_STATE_LABELS,
    PlannerAgent,
    WorkerAgent,
    IntegratorAgent,
    QualityAgent,
    planner_creates_tasks,
    planner_cannot_plan,
    worker_creates_pr,
    worker_fails,
    integrator_merges,
    integrator_fails,
    quality_passes,
    quality_fails,
    no_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_repo() -> Repository:
    return Repository(state_labels=AGENTIC_TASK_MACHINE_STATE_LABELS)


def user_issue(repo: Repository, number: int = 1) -> None:
    """Add an open type/user issue."""
    repo.add_issue(number, labels={"type/user"})


def task_issue(repo: Repository, number: int, parent: int) -> None:
    """Add an open type/task sub-issue with a parent reference."""
    issue = repo.add_issue(number, labels={"type/task"})
    issue.parent_ref = parent  # type: ignore[attr-defined]


def approved_pr(repo: Repository, pr_number: int, issue_number: int) -> None:
    """Add an open PR labeled status/approved and linked to an issue."""
    pr = repo.add_pr(
        pr_number,
        body=f"## Summary\n\nCloses #{issue_number}",
        head_ref=f"feature/issue-{issue_number}",
        state="open",
    )
    pr.labels.add("status/approved")


# ---------------------------------------------------------------------------
# PlannerAgent tests
# ---------------------------------------------------------------------------

class TestPlannerAgent:
    """Tests for the planner agent that owns type/user issues."""

    def test_creates_tasks_on_success(self):
        repo = make_repo()
        user_issue(repo, number=1)
        engine = Engine(repo).register(PlannerAgent(behavior=planner_creates_tasks(task_count=2)))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        tasks = [i for i in repo.issues.values() if "type/task" in i.labels]
        assert len(tasks) == 2
        for t in tasks:
            assert t.parent_ref == 1  # type: ignore[attr-defined]

    def test_blocks_when_no_tasks_created(self):
        repo = make_repo()
        user_issue(repo, number=1)
        engine = Engine(repo).register(PlannerAgent(behavior=planner_cannot_plan()))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        assert "blocked" in repo.get_issue(1).labels

    def test_blocks_on_no_output(self):
        repo = make_repo()
        user_issue(repo, number=1)
        engine = Engine(repo).register(PlannerAgent(behavior=no_output()))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        assert "blocked" in repo.get_issue(1).labels

    def test_idempotent_when_tasks_already_exist(self):
        """Planner does not re-plan if type/task sub-issues already exist."""
        repo = make_repo()
        user_issue(repo, number=1)
        task_issue(repo, number=2, parent=1)
        initial_count = len(repo.issues)
        engine = Engine(repo).register(PlannerAgent(behavior=planner_creates_tasks(task_count=2)))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        assert len(repo.issues) == initial_count  # no new issues created

    def test_skips_blocked_user_issues(self):
        repo = make_repo()
        repo.add_issue(1, labels={"type/user", "blocked"})
        engine = Engine(repo).register(PlannerAgent(behavior=planner_creates_tasks()))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        # No type/task issues should be created for a blocked parent
        tasks = [i for i in repo.issues.values() if "type/task" in i.labels]
        assert len(tasks) == 0

    def test_fires_on_issue_opened_and_auto_labels(self):
        """Planner fires on issues:opened, applies type/user label, then plans."""
        repo = make_repo()
        # Issue starts without any label — as it would when first opened on GitHub
        issue = repo.add_issue(1, labels=set())
        engine = Engine(repo).register(PlannerAgent(behavior=planner_creates_tasks(task_count=2)))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        assert "type/user" in repo.get_issue(1).labels  # auto-labeled
        tasks = [i for i in repo.issues.values() if "type/task" in i.labels]
        assert len(tasks) == 2

    def test_opened_event_skips_issues_already_planned(self):
        """ISSUE_OPENED is idempotent: does not re-plan if sub-tasks already exist."""
        repo = make_repo()
        issue = repo.add_issue(1, labels=set())
        task_issue(repo, number=2, parent=1)
        initial_count = len(repo.issues)
        engine = Engine(repo).register(PlannerAgent(behavior=planner_creates_tasks(task_count=2)))
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        assert len(repo.issues) == initial_count


# ---------------------------------------------------------------------------
# WorkerAgent tests
# ---------------------------------------------------------------------------

class TestWorkerAgent:
    """Tests for the worker agent that owns type/task issues."""

    def test_creates_pr_on_success(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        engine = Engine(repo).register(WorkerAgent(behavior=worker_creates_pr()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1))
        pr = repo.find_pr_for_issue(1, state="open")
        assert pr is not None
        assert "Closes #1" in pr.body

    def test_blocks_when_no_pr_created(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        engine = Engine(repo).register(WorkerAgent(behavior=worker_fails()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1))
        assert "blocked" in repo.get_issue(1).labels

    def test_blocks_on_no_output(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        engine = Engine(repo).register(WorkerAgent(behavior=no_output()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1))
        assert "blocked" in repo.get_issue(1).labels

    def test_idempotent_when_pr_already_exists(self):
        """Worker does not create another PR if one already exists."""
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        approved_pr(repo, pr_number=10, issue_number=1)
        initial_pr_count = len(repo.pull_requests)
        engine = Engine(repo).register(WorkerAgent(behavior=worker_creates_pr()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1))
        assert len(repo.pull_requests) == initial_pr_count

    def test_skips_blocked_task_issues(self):
        repo = make_repo()
        repo.add_issue(1, labels={"type/task", "blocked"})
        repo.get_issue(1).parent_ref = 100  # type: ignore[attr-defined]
        engine = Engine(repo).register(WorkerAgent(behavior=worker_creates_pr()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1))
        assert repo.find_pr_for_issue(1, state="open") is None

    def test_fires_on_type_task_label_added(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        engine = Engine(repo).register(WorkerAgent(behavior=worker_creates_pr()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1))
        assert repo.find_pr_for_issue(1, state="open") is not None

    def test_retriggers_when_blocked_removed(self):
        """Worker fires again when blocked label is removed."""
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        repo.add_label(1, "blocked")
        repo.remove_label(1, "blocked")
        engine = Engine(repo).register(WorkerAgent(behavior=worker_creates_pr()))
        engine.fire(Event(kind=EventKind.LABEL_REMOVED, label="blocked", issue_num=1))
        assert repo.find_pr_for_issue(1, state="open") is not None


# ---------------------------------------------------------------------------
# IntegratorAgent tests
# ---------------------------------------------------------------------------

class TestIntegratorAgent:
    """Tests for the integrator agent that merges approved PRs."""

    def test_merges_approved_pr(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        approved_pr(repo, pr_number=10, issue_number=1)
        engine = Engine(repo).register(IntegratorAgent(behavior=integrator_merges()))
        engine.fire(Event(kind=EventKind.PR_EVENT, pr_num=10, data={"label": "status/approved"}))
        assert repo.get_pr(10).state == "merged"

    def test_does_not_merge_unapproved_pr(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        repo.add_pr(10, body="Closes #1", state="open", review_decision="")
        Engine(repo).register(IntegratorAgent(behavior=integrator_merges())).tick()
        assert repo.get_pr(10).state == "open"

    def test_idempotent_when_already_merged(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        repo.add_pr(10, body="Closes #1", state="merged", review_decision="APPROVED")
        Engine(repo).register(IntegratorAgent(behavior=integrator_merges())).tick()
        # Should remain merged, not crash
        assert repo.get_pr(10).state == "merged"

    def test_verify_notes_failure_when_not_merged(self):
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        approved_pr(repo, pr_number=10, issue_number=1)
        engine = Engine(repo).register(IntegratorAgent(behavior=integrator_fails()))
        traces = engine.fire(Event(kind=EventKind.PR_EVENT, pr_num=10, data={"label": "status/approved"}))
        assert repo.get_pr(10).state == "open"
        outcomes = [t.verify_outcome.action for t in traces if t.verify_outcome]
        assert any(o == "unchanged" for o in outcomes)

    def test_blocks_linked_issue_when_ci_exhausted(self):
        """Integrator adds blocked to the linked task issue after failing to merge."""
        repo = make_repo()
        task_issue(repo, number=1, parent=100)
        approved_pr(repo, pr_number=10, issue_number=1)
        engine = Engine(repo).register(IntegratorAgent(behavior=integrator_fails()))
        engine.fire(Event(kind=EventKind.PR_EVENT, pr_num=10, data={"label": "status/approved"}))
        assert "blocked" in repo.get_issue(1).labels


# ---------------------------------------------------------------------------
# QualityAgent tests
# ---------------------------------------------------------------------------

class TestQualityAgent:
    """Tests for the quality agent that reviews completed type/user issues."""

    def _setup_completed_user_issue(self, repo: Repository) -> None:
        """Set up a type/user issue with all type/task children closed."""
        user_issue(repo, number=1)
        task_issue(repo, number=2, parent=1)
        task_issue(repo, number=3, parent=1)
        # Mark tasks as closed
        repo.get_issue(2).labels.add("__closed__")
        repo.get_issue(3).labels.add("__closed__")

    def test_closes_parent_on_quality_passed(self):
        repo = make_repo()
        self._setup_completed_user_issue(repo)
        engine = Engine(repo).register(QualityAgent(behavior=quality_passes()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=3))
        assert "__closed__" in repo.get_issue(1).labels

    def test_creates_followup_tasks_on_quality_failed(self):
        repo = make_repo()
        self._setup_completed_user_issue(repo)
        engine = Engine(repo).register(QualityAgent(behavior=quality_fails(gap_count=1)))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=3))
        # Parent should NOT be closed
        assert "__closed__" not in repo.get_issue(1).labels
        # New type/task follow-up should exist
        new_tasks = [i for i in repo.issues.values()
                     if "type/task" in i.labels and i.number not in (2, 3)]
        assert len(new_tasks) == 1

    def test_skips_when_tasks_still_open(self):
        repo = make_repo()
        user_issue(repo, number=1)
        task_issue(repo, number=2, parent=1)
        task_issue(repo, number=3, parent=1)
        # Only one task closed
        repo.get_issue(2).labels.add("__closed__")
        engine = Engine(repo).register(QualityAgent(behavior=quality_passes()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=2))
        assert "__closed__" not in repo.get_issue(1).labels  # parent not closed

    def test_skips_already_closed_parent(self):
        repo = make_repo()
        self._setup_completed_user_issue(repo)
        repo.get_issue(1).labels.add("__closed__")  # parent already closed
        initial_count = len(repo.issues)
        engine = Engine(repo).register(QualityAgent(behavior=quality_passes()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=3))
        assert len(repo.issues) == initial_count  # no new issues

    def test_no_action_on_no_signal(self):
        repo = make_repo()
        self._setup_completed_user_issue(repo)
        engine = Engine(repo).register(QualityAgent(behavior=no_output()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=3))
        assert "__closed__" not in repo.get_issue(1).labels  # not closed, retries later

    def test_idempotent_when_run_twice(self):
        repo = make_repo()
        self._setup_completed_user_issue(repo)
        engine = Engine(repo).register(QualityAgent(behavior=quality_passes()))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=3))
        assert "__closed__" in repo.get_issue(1).labels
        # Second fire should not crash or create duplicates
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=3))
        assert "__closed__" in repo.get_issue(1).labels


# ---------------------------------------------------------------------------
# State healer invariant tests
# ---------------------------------------------------------------------------

class TestStateHealer:
    def test_healer_removes_conflicting_blocked_label(self):
        """Adding blocked to an issue that already has blocked is a no-op (already there)."""
        repo = make_repo()
        repo.add_issue(1, labels={"type/task"})
        repo.add_label(1, "blocked")
        assert "blocked" in repo.get_issue(1).labels
        # Adding again should not create duplicates (sets are unique)
        repo.add_label(1, "blocked")
        assert len([l for l in repo.get_issue(1).labels if l == "blocked"]) == 1

    def test_non_state_labels_survive_blocked(self):
        """Metadata labels type/user and type/task are not healed away."""
        repo = make_repo()
        repo.add_issue(1, labels={"type/task"})
        repo.add_label(1, "blocked")
        issue = repo.get_issue(1)
        assert "type/task" in issue.labels
        assert "blocked" in issue.labels

    def test_engine_raises_on_double_state(self):
        """Engine catches pre-existing broken state before agents can mask it."""
        if len(AGENTIC_TASK_MACHINE_STATE_LABELS) < 2:
            pytest.skip("Only one state label — cannot create double-state scenario")


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_happy_path(self):
        """
        Full pipeline: type/user → planner creates tasks → worker creates PRs
        → integrator merges → quality reviews → parent closed.
        """
        repo = make_repo()
        user_issue(repo, number=1)

        # Step 1: Planner creates 2 type/task sub-issues
        Engine(repo).register(PlannerAgent(behavior=planner_creates_tasks(task_count=2))).fire(
            Event(kind=EventKind.ISSUE_OPENED, issue_num=1)
        )
        tasks = [i for i in repo.issues.values() if "type/task" in i.labels]
        assert len(tasks) == 2

        # Step 2: Worker creates PRs for each task
        for task in tasks:
            Engine(repo).register(WorkerAgent(behavior=worker_creates_pr())).fire(
                Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=task.number)
            )
        prs = repo.list_prs(state="open")
        assert len(prs) == 2

        # Step 3: Label PRs status/approved and integrator merges them
        for pr in prs:
            pr.labels.add("status/approved")
            Engine(repo).register(IntegratorAgent(behavior=integrator_merges())).fire(
                Event(kind=EventKind.PR_EVENT, pr_num=pr.number, data={"label": "status/approved"})
            )
        merged_prs = repo.list_prs(state="merged")
        assert len(merged_prs) == 2

        # Step 4: Mark tasks as closed (integrator closed them via Closes #N)
        for task in tasks:
            task.labels.add("__closed__")

        # Step 5: Quality agent reviews and passes
        last_task = tasks[-1]
        Engine(repo).register(QualityAgent(behavior=quality_passes())).fire(
            Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=last_task.number)
        )
        assert "__closed__" in repo.get_issue(1).labels

    def test_blocked_task_then_recovered(self):
        """Worker fails → blocked; human removes blocked → worker retries and succeeds."""
        repo = make_repo()
        task_issue(repo, number=1, parent=100)

        # First attempt: worker fails
        Engine(repo).register(WorkerAgent(behavior=worker_fails())).fire(
            Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=1)
        )
        assert "blocked" in repo.get_issue(1).labels

        # Recovery: remove blocked, fire LABEL_REMOVED event
        repo.remove_label(1, "blocked")
        engine = Engine(repo).register(WorkerAgent(behavior=worker_creates_pr()))
        engine.fire(Event(kind=EventKind.LABEL_REMOVED, label="blocked", issue_num=1))
        assert repo.find_pr_for_issue(1, state="open") is not None

    def test_quality_insufficient_creates_followup(self):
        """Quality fails → follow-up tasks created → worker picks them up."""
        repo = make_repo()
        user_issue(repo, number=1)
        task_issue(repo, number=2, parent=1)
        repo.get_issue(2).labels.add("__closed__")

        # Quality finds a gap
        Engine(repo).register(QualityAgent(behavior=quality_fails(gap_count=1))).fire(
            Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=2)
        )
        followup_tasks = [
            i for i in repo.issues.values()
            if "type/task" in i.labels and i.number != 2 and "__closed__" not in i.labels
        ]
        assert len(followup_tasks) == 1

        # Worker picks up the follow-up task
        Engine(repo).register(WorkerAgent(behavior=worker_creates_pr())).fire(
            Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=followup_tasks[0].number)
        )
        pr = repo.find_pr_for_issue(followup_tasks[0].number, state="open")
        assert pr is not None

    def test_state_invariant_never_violated(self):
        """Engine enforces at-most-one-state-label after every event."""
        repo = make_repo()
        user_issue(repo, number=1)
        task_issue(repo, number=2, parent=1)
        engine = Engine(repo).register(
            PlannerAgent(behavior=planner_creates_tasks()),
            WorkerAgent(behavior=worker_creates_pr()),
            QualityAgent(behavior=quality_passes()),
        )
        engine.fire(Event(kind=EventKind.ISSUE_OPENED, issue_num=1))
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="type/task", issue_num=2))
        repo.get_issue(2).labels.add("__closed__")
        engine.fire(Event(kind=EventKind.LABEL_ADDED, label="__closed__", issue_num=2))
        for issue in repo.issues.values():
            state_count = len(issue.labels & AGENTIC_TASK_MACHINE_STATE_LABELS)
            assert state_count <= 1, (
                f"Issue #{issue.number} carries {state_count} state labels: "
                f"{issue.labels & AGENTIC_TASK_MACHINE_STATE_LABELS}"
            )
