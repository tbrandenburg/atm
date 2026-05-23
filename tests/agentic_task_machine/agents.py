"""
Concrete agents for agentic-task-machine.

The agentic-task-machine state machine is driven by issue types and GitHub open/closed state
rather than mutually exclusive state labels.  The only state label is 'blocked'.

Agents:
  PlannerAgent     — processes type/user issues that have no type/task children yet
  WorkerAgent      — processes type/task issues that have no linked open PR yet
  IntegratorAgent  — processes PRs labeled status/approved (stateless)
  QualityAgent     — processes type/user issues where all type/task children are closed
"""
from __future__ import annotations

from tests.sim.agents import (
    AgentResult,
    Behavior,
    Event,
    EventKind,
    StateAgent,
    StatelessAgent,
    VerifyOutcome,
)
from tests.sim.models import Issue, PullRequest, Repository


# ---------------------------------------------------------------------------
# State label set — must match core-state-heal.yml exactly
# ---------------------------------------------------------------------------

AGENTIC_TASK_MACHINE_STATE_LABELS: frozenset[str] = frozenset({"blocked"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task_issues_for_parent(repo: Repository, parent_num: int) -> list[Issue]:
    """Return all type/task issues that reference this parent."""
    return [
        i for i in repo.list_issues(label="type/task")
        if any(f"Parent issue: #{parent_num}" in c for c in [i.comments[0]] if i.comments)
        or f"Parent issue: #{parent_num}" in getattr(i, "body", "")
    ]


def _task_issues_for_parent_by_body(repo: Repository, parent_num: int) -> list[Issue]:
    """Find type/task sub-issues by checking a 'parent_ref' metadata attribute."""
    result = []
    for issue in repo.list_issues(label="type/task"):
        parent = getattr(issue, "parent_ref", None)
        if parent == parent_num:
            result.append(issue)
    return result


# ---------------------------------------------------------------------------
# Built-in behaviors
# ---------------------------------------------------------------------------

def planner_creates_tasks(task_count: int = 2) -> Behavior:
    """Planner stages N type/task specs (written as files in prod; metadata here)."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        staged = [
            {"title": f"Task {i + 1} for issue #{issue.number}", "parent": issue.number}
            for i in range(task_count)
        ]
        return AgentResult(
            comments=[
                f"Drafted {task_count} type/task sub-tasks (verify step will create GitHub issues): "
                + ", ".join(s["title"] for s in staged)
            ],
            metadata={"staged_tasks": staged},
        )
    return _behavior


def planner_cannot_plan() -> Behavior:
    """Planner fails to create any tasks."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        return AgentResult()
    return _behavior


def worker_creates_pr() -> Behavior:
    """Worker creates a branch and opens a PR."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        next_pr = max(repo.pull_requests.keys(), default=0) + 1
        repo.add_pr(
            next_pr,
            body=f"## Summary\n\nCloses #{issue.number}",
            head_ref=f"feature/issue-{issue.number}",
            review_decision="",
            state="open",
        )
        return AgentResult(
            comments=[f"<!-- PR-CREATED -->\nPR #{next_pr} opened."],
            metadata={"pr_number": next_pr},
        )
    return _behavior


def worker_fails() -> Behavior:
    """Worker encounters a blocker and cannot create a PR."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        return AgentResult()
    return _behavior


def integrator_merges() -> Behavior:
    """Integrator merges the PR."""
    def _behavior(repo: Repository, pr: PullRequest) -> AgentResult:
        repo.merge_pr(pr.number)
        # Close linked issue
        for issue in repo.issues.values():
            if pr.links_issue(issue.number):
                issue.labels.add("__closed__")  # sentinel for closed state
        return AgentResult(
            metadata={"merged_pr": pr.number},
        )
    return _behavior


def integrator_fails() -> Behavior:
    """Integrator cannot merge (CI stuck after 3 attempts) — blocks the linked task issue."""
    def _behavior(repo: Repository, pr: PullRequest) -> AgentResult:
        # Find and block the linked task issue
        for issue in repo.issues.values():
            if pr.links_issue(issue.number):
                repo.add_label(issue.number, "blocked")
        return AgentResult()
    return _behavior


def quality_passes() -> Behavior:
    """Quality agent determines the solution is sufficient."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        return AgentResult(
            comments=[
                "<!-- QUALITY-PASSED -->\n✅ Quality review passed. All criteria met."
            ],
        )
    return _behavior


def quality_fails(gap_count: int = 1) -> Behavior:
    """Quality agent finds gaps and stages follow-up task specs (written as files in prod)."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        staged = [
            {"title": f"Gap {i + 1} for issue #{issue.number}", "parent": issue.number}
            for i in range(gap_count)
        ]
        return AgentResult(
            comments=[
                f"<!-- QUALITY-FAILED -->\n\u274c Gaps found. "
                "(Verify step will create follow-up type/task issues from task files.)"
            ],
            metadata={"staged_tasks": staged},
        )
    return _behavior


def no_output() -> Behavior:
    """Agent produces no output (crash / timeout)."""
    def _behavior(repo: Repository, issue: Issue) -> AgentResult:
        return AgentResult()
    return _behavior


# ---------------------------------------------------------------------------
# PlannerAgent — owns type/user issues without type/task sub-issues
# ---------------------------------------------------------------------------

class PlannerAgent(StatelessAgent):
    """
    Processes open type/user issues that have no type/task children.

    Mirrors: .github/workflows/sm-user.yml
    """

    def __init__(self, behavior: Behavior | None = None) -> None:
        self._behavior = behavior or planner_creates_tasks()

    def entry_trigger(self, event: Event) -> bool:
        return (
            event.kind == EventKind.ISSUE_OPENED
        )

    def entry_action(self, repo: Repository, event: Event) -> list[Issue]:
        candidates = []
        if event.kind == EventKind.ISSUE_OPENED:
            # Mirrors the auto-label step in sm-user.yml prepare
            repo.add_label(event.issue_num, "type/user")
        issues_to_check = [repo.get_issue(event.issue_num)] if event.issue_num else []
        for issue in issues_to_check:
            if "type/user" not in issue.labels:
                continue
            if "blocked" in issue.labels or "__closed__" in issue.labels:
                continue
            # Skip if already has sub-tasks
            children = _task_issues_for_parent_by_body(repo, issue.number)
            if not children:
                candidates.append(issue)
        return candidates

    def do_action(self, repo: Repository, issue: Issue) -> AgentResult:
        return self._behavior(repo, issue)

    def exit_action(
        self, repo: Repository, issue: Issue, result: AgentResult
    ) -> VerifyOutcome:
        # Mirrors the verify step: create issues from staged task specs.
        staged = result.metadata.get("staged_tasks", [])
        for spec in staged:
            next_num = max(repo.issues.keys(), default=0) + 1
            task = repo.add_issue(next_num, labels={"type/task"}, comments=[])
            task.parent_ref = spec["parent"]  # type: ignore[attr-defined]
        # Re-check: did the verify step successfully create any children?
        children = _task_issues_for_parent_by_body(repo, issue.number)
        if children:
            return VerifyOutcome(
                action="promoted",
                from_state="type/user:unplanned",
                to_state="type/user:planned",
                reason="sub-tasks-created",
            )
        # No children → block the parent
        repo.add_label(issue.number, "blocked")
        return VerifyOutcome(
            action="blocked",
            from_state="type/user:unplanned",
            to_state="blocked",
            reason="no-tasks-created",
            labels_added=["blocked"],
        )


# ---------------------------------------------------------------------------
# WorkerAgent — owns open type/task issues without a linked PR
# ---------------------------------------------------------------------------

class WorkerAgent(StatelessAgent):
    """
    Processes open type/task issues that have no linked open PR.

    Mirrors: .github/workflows/sm-task.yml
    """

    def __init__(self, behavior: Behavior | None = None) -> None:
        self._behavior = behavior or worker_creates_pr()

    def entry_trigger(self, event: Event) -> bool:
        return (
            (event.kind == EventKind.LABEL_ADDED and event.label == "type/task")
            or (event.kind == EventKind.LABEL_REMOVED and event.label == "blocked")
        )

    def entry_action(self, repo: Repository, event: Event) -> list[Issue]:
        issues_to_check = [repo.get_issue(event.issue_num)] if event.issue_num else []
        candidates = []
        for issue in issues_to_check:
            if "type/task" not in issue.labels:
                continue
            if "blocked" in issue.labels or "__closed__" in issue.labels:
                continue
            # Skip if already has a linked open PR
            existing_pr = repo.find_pr_for_issue(issue.number, state="open")
            if existing_pr is None:
                candidates.append(issue)
        return candidates

    def do_action(self, repo: Repository, issue: Issue) -> AgentResult:
        return self._behavior(repo, issue)

    def exit_action(
        self, repo: Repository, issue: Issue, result: AgentResult
    ) -> VerifyOutcome:
        # Verify: does a linked open PR now exist?
        pr = repo.find_pr_for_issue(issue.number, state="open")
        if pr is not None:
            return VerifyOutcome(
                action="promoted",
                from_state="type/task:unworked",
                to_state="type/task:pr-created",
                reason="pr-linked",
            )
        # No PR → block the task
        repo.add_label(issue.number, "blocked")
        return VerifyOutcome(
            action="blocked",
            from_state="type/task:unworked",
            to_state="blocked",
            reason="no-pr-created",
            labels_added=["blocked"],
        )


# ---------------------------------------------------------------------------
# IntegratorAgent — stateless, processes PRs labeled status/approved
# ---------------------------------------------------------------------------

class IntegratorAgent(StatelessAgent):
    """
    Merges PRs labeled status/approved to main.

    Mirrors: .github/workflows/agent-integrator.yml
    """

    def __init__(self, behavior: Behavior | None = None) -> None:
        self._behavior = behavior or integrator_merges()

    def entry_trigger(self, event: Event) -> bool:
        return event.kind == EventKind.PR_EVENT and event.data.get("label") == "status/approved"

    def entry_action(self, repo: Repository, event: Event) -> list[PullRequest]:
        if event.pr_num:
            pr = repo.get_pr(event.pr_num)
            if pr.state == "open" and "status/approved" in pr.labels:
                return [pr]
        return []

    def do_action(self, repo: Repository, pr: PullRequest) -> AgentResult:
        return self._behavior(repo, pr)

    def exit_action(
        self, repo: Repository, pr: PullRequest, result: AgentResult
    ) -> VerifyOutcome:
        pr = repo.get_pr(pr.number)
        if pr.state == "merged":
            return VerifyOutcome(
                action="promoted",
                from_state="pr:open",
                to_state="pr:merged",
                reason="merged",
            )
        return VerifyOutcome(
            action="unchanged",
            from_state="pr:open",
            to_state="pr:open",
            reason="merge-failed",
        )


# ---------------------------------------------------------------------------
# QualityAgent — stateless, processes type/user issues with all tasks closed
# ---------------------------------------------------------------------------

class QualityAgent(StatelessAgent):
    """
    Reviews solution quality when all type/task children of a type/user issue are closed.

    Mirrors: .github/workflows/agent-quality.yml
    """

    def __init__(self, behavior: Behavior | None = None) -> None:
        self._behavior = behavior or quality_passes()

    def entry_trigger(self, event: Event) -> bool:
        return event.kind == EventKind.LABEL_ADDED and event.label == "__closed__"

    def entry_action(self, repo: Repository, event: Event) -> list[Issue]:
        candidates = []
        for issue in repo.list_issues(label="type/user"):
            if "__closed__" in issue.labels or "blocked" in issue.labels:
                continue
            # Check all type/task children are closed
            children = _task_issues_for_parent_by_body(repo, issue.number)
            if not children:
                continue
            all_closed = all("__closed__" in c.labels for c in children)
            if all_closed:
                candidates.append(issue)
        return candidates

    def do_action(self, repo: Repository, issue: Issue) -> AgentResult:
        return self._behavior(repo, issue)

    def exit_action(
        self, repo: Repository, issue: Issue, result: AgentResult
    ) -> VerifyOutcome:
        issue = repo.get_issue(issue.number)
        if issue.has_signal("<!-- QUALITY-PASSED -->"):
            issue.labels.add("__closed__")
            return VerifyOutcome(
                action="promoted",
                from_state="type/user:quality-pending",
                to_state="type/user:closed",
                reason="quality-passed",
                labels_added=["__closed__"],
            )
        if issue.has_signal("<!-- QUALITY-FAILED -->"):
            # Mirrors the verify step: create follow-up tasks from staged specs.
            staged = result.metadata.get("staged_tasks", [])
            for spec in staged:
                next_num = max(repo.issues.keys(), default=0) + 1
                task = repo.add_issue(next_num, labels={"type/task"}, comments=[])
                task.parent_ref = spec["parent"]  # type: ignore[attr-defined]
            return VerifyOutcome(
                action="promoted",
                from_state="type/user:quality-pending",
                to_state="type/user:followup-created",
                reason="quality-failed",
            )
        # No signal → do nothing, retry on next schedule
        return VerifyOutcome(
            action="unchanged",
            from_state="type/user:quality-pending",
            to_state="type/user:quality-pending",
            reason="no-signal",
        )
