# agentic-task-machine

## Goal
Build a fully autonomous, GitHub Actions–driven issue-resolution system where user-facing
feature requests (`type/user`) are broken down into parallelisable sub-tasks (`type/task`),
implemented end-to-end by LLM agents, and validated for quality — all without human
intervention unless an agent is explicitly blocked.

---

## Purpose
Replace the manual loop of: read issue → design tasks → assign developer → review → merge →
verify quality with an automated pipeline of LLM agents. Humans define what to build
(via `type/user` issues); the machine figures out how, builds it, and verifies it.

---

## Requirements
- System MUST auto-label as `type/user` any issue opened by a non-bot actor (human-created
  issues do not carry the label at creation time).
- System MUST trigger the planner agent when a new `type/user` issue is labeled.
- System MUST create `type/task` sub-issues (each referencing the parent) without human
  intervention.
- System MUST trigger the worker agent for each new `type/task` issue atomically:
  branch → implement → PR → self-review + approval.
- System MUST trigger the integrator to merge approved, CI-green PRs to `main` using a PAT.
- System MUST trigger the quality agent when all `type/task` sub-issues of a `type/user`
  issue are closed.
- System MUST create follow-up `type/task` issues when the quality agent deems the
  solution insufficient.
- System MUST close the parent `type/user` issue when the quality agent deems the solution
  sufficient.
- System MUST add `blocked` to any `type/task` issue whose worker agent fails; human
  removes `blocked` to retry.
- System MUST NOT re-plan a `type/user` issue that already has `type/task` sub-issues.
- System MUST NOT re-process a `type/task` issue that already has a linked PR.
- System MUST run on github.com without a corporate proxy.
- System MUST run on standard GitHub-hosted runners.

---

## Inputs
- GitHub issues opened by humans in this repository. All such issues are automatically
  labeled `type/user` by the planner workflow on the `issues: opened` event.
  Human-created issues carry no label at the moment of creation.

## Outputs
- `type/task` sub-issues (implementation plans, one per parallelisable feature slice).
- Feature branches and pull requests per sub-task.
- Merged commits to `main`.
- Closed `type/user` issues (on quality confirmation).

---

## Environment and Constraints
- Runner: `ubuntu-latest`
- Proxy: none
- Merge PAT secret: `AGENT_GH_TOKEN` (required for integrator to push to protected branches)
- LLM model: `opencode/big-pickle`
- Branch protection: approved PR required for merge to `main`
- Labels in use: `type/user`, `type/task`, `blocked`

---

## Agentic State Machine

| State | Entry Condition | Agent | Core Action | Exit Condition | Next Step |
|---|---|---|---|---|---|
| **New user issue** | Issue opened by a human (non-bot) — `type/user` label auto-applied on `issues: opened` | Planner | Break user issue into parallelisable `type/task` sub-issues with implementation plans | `type/task` sub-issues exist in repo referencing parent | Sub-issues trigger worker independently |
| **New task issue** | Issue opened with `type/task` label _or_ `blocked` removed | Worker | Create branch → implement → open PR → self-review + label PR `status/approved` | Linked open PR exists | Integrator picks up PR labeled `status/approved` |
| **Merge** | `status/approved` label added to PR (by worker self-review) | Integrator | Ensure CI is green (fix if failing) → merge PR to `main` (resolve conflicts if needed); close linked `type/task` issue | PR merged, issue closed | Last task closure triggers quality |
| **Quality check** | All `type/task` for a `type/user` are closed | Quality | Review all merged PRs + issue comments; judge sufficiency | Signal posted | Sufficient → close `type/user`; insufficient → new `type/task` issues |

---

## Stateless / Event-Driven Agents

| Trigger | Workflow | Action | Condition | Failure Handling |
|---|---|---|---|---|
| `issues: closed` (type/task) | `agent-quality.yml` | Review solution quality for parent `type/user` | All sibling `type/task` closed + parent still open | Post comment; use `workflow_dispatch` to retry |
| `pull_request: labeled` (`status/approved`) | `agent-integrator.yml` | Ensure CI passes (diagnose and fix if failing) → merge PR to `main` using PAT | `status/approved` label present, no `CHANGES_REQUESTED` reviews | Post comment on PR, leave PR open for next run |

---

## Edge Cases

- If planner fires but `type/task` sub-issues already exist for the parent → skip (prepare step queries for existing sub-issues).
- If worker fires but a linked PR already exists for the `type/task` issue → skip (prepare step queries open PRs).
- If worker fails (any step) → add `blocked` label; `issues: unlabeled` event on `blocked` immediately retriggers worker.
- If quality fires but not all `type/task` issues are closed → skip and wait.
- If quality fires but parent `type/user` is already closed → skip.
- If quality agent produces no signal → post comment; use `workflow_dispatch` to retry.
- If integrator encounters a merge conflict → agent resolves via `git` and force-pushes branch before re-merging.
- If integrator encounters CI failure → agent inspects CI logs, pushes a fix commit, and waits for CI to re-run before merging.

---

## Acceptance Criteria
- [ ] A `type/user` issue automatically receives `type/task` sub-issues within one workflow cycle.
- [ ] Each `type/task` issue results in a branch, implementation, and a PR labeled `status/approved` — without human action.
- [ ] When a PR is labeled `status/approved` by the worker self-review, the integrator ensures CI is green (fixing if needed) and merges to `main` automatically.
- [ ] When all `type/task` issues for a `type/user` are closed, the quality agent runs and either closes the parent or creates follow-up tasks.
- [ ] A failed worker adds `blocked`; removing `blocked` immediately retriggers the worker.
- [ ] No `type/user` or `type/task` issue is processed twice (idempotency guaranteed).

---

## Technical Notes
- **Sub-issue parent reference**: Every `type/task` issue body must contain a line
  `Parent issue: #N` (where N is the `type/user` issue number). The quality agent uses
  this to locate siblings.
- **Atomic task creation**: The planner and quality agents write temporary
  `.agentic-task-machine/tasks/{parent}-{n}-{slug}.md` files (ignored by git). The verify step reads
  these files and creates GitHub issues with `gh issue create --label "type/task"` in one
  atomic command — ensuring `type/task` is present on the issue from the moment it exists.
  This makes the sm-user.yml trigger filter reliable: any `issues: opened` event where
  the issue already carries `type/task` is skipped (agent-created); all others are human.
- **Proxy**: No proxy is configured; workflows use direct github.com/network access.
- **PAT scope**: `AGENT_GH_TOKEN` must have `repo` scope (push to protected branch).
- **Simulation tests**: pytest-based simulation layer under `tests/` validates state
  machine invariants without hitting GitHub.
- **OpenCode model**: `opencode/big-pickle` (set in `.github/config/config.yml`).
- **WIP limit**: configurable via `max_wip` in `.github/config/config.yml`.
