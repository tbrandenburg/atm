# Implementation Plan: agentic-task-machine

> Context: [docs/PRD.md](../PRD.md)

## Plan Metadata

| Field | Value |
|---|---|
| **Mode** | New system |
| **Complexity** | Medium |
| **Primary Workflows Affected** | `sm-user.yml`, `sm-task.yml`, `agent-integrator.yml`, `agent-quality.yml`, `core-state-heal.yml` |
| **New States** | none (open/closed are the states; `blocked` is the only flag label) |
| **New Agents** | `planner`, `worker`, `integrator`, `quality` |

---

## Context References

Files to read **before implementing**. Understand each before touching any file.

| File | Why |
|---|---|
| `.github/skills/agentic-workflow-system/assets/examples/core-opencode-run.yml` | Copy verbatim as-is |
| `.github/skills/agentic-workflow-system/assets/examples/core-state-heal.yml` | Template — adapt state list to `blocked` only |
| `.github/skills/agentic-workflow-system/assets/examples/sm-workflow-template.yml` | Template for `sm-user.yml` and `sm-task.yml` |
| `.github/skills/agentic-workflow-system/assets/examples/agent-workflow-template.yml` | Template for `agent-integrator.yml` and `agent-quality.yml` |
| `.github/skills/agentic-workflow-system/assets/examples/agents/planner.md` | Mirror persona format |
| `.github/skills/agentic-workflow-system/assets/examples/commands/ghaw-plan-issue.md` | Mirror command format |

---

## Patterns to Follow

**Signal marker naming:** `<!-- VERB-NOUN -->` in all caps, e.g. `<!-- PR-CREATED -->`, `<!-- QUALITY-PASSED -->`

**Verify step fallback:** always `gh issue edit --add-label blocked` when expected signal is absent, then `exit 1`

**State label format:** no namespace prefix, kebab-case (`blocked`)

**Metadata label format:** namespaced, kebab-case (`type/user`, `type/task`)

**Sub-issue parent reference:** every `type/task` body must contain `Parent issue: #N`

**Atomic task creation:** planner and quality agents write `.agentic-task-machine/tasks/{parent}-{n}-{slug}.md`
files (gitignored). Format: line 1 = `title: {title}`, line 2 blank, lines 3+ = issue body.
The verify step reads these files and calls `gh issue create --label "type/task"` atomically.

**sm-user trigger filter:** `!contains(github.event.issue.labels.*.name, 'type/task')` —
reliable because `type/task` is added at issue creation time by the verify step, never
separately. Any issue opened without it is definitively human-created.

**Proxy:** no proxy is configured; jobs use direct github.com/network access.

---

## New Files to Create

| File | Purpose |
|------|---------|
| `.github/workflows/core-opencode-run.yml` | Reusable LLM runner — copy verbatim |
| `.github/workflows/core-state-heal.yml` | State exclusivity enforcer (`blocked` only) |
| `.github/config/config.yml` | Model and WIP config |
| `.github/workflows/sm-user.yml` | Planner agent — processes `type/user` issues |
| `.github/workflows/sm-task.yml` | Worker agent — processes `type/task` issues atomically |
| `.github/workflows/agent-integrator.yml` | Integrator — fires on `status/approved` label added to PR, merges to main |
| `.github/workflows/agent-quality.yml` | Quality agent — fires on `type/task` issue close |
| `.opencode/agent/planner.md` | Planner persona |
| `.opencode/agent/worker.md` | Worker persona |
| `.opencode/agent/integrator.md` | Integrator persona |
| `.opencode/agent/quality.md` | Quality persona |
| `.opencode/commands/agentic-task-machine-plan-user-issue.md` | Planner command: break `type/user` → `type/task` sub-issues |
| `.opencode/commands/agentic-task-machine-work-task-issue.md` | Worker command: branch → implement → PR → self-review + approve |
| `.opencode/commands/agentic-task-machine-integrate.md` | Integrator command: ensure CI green → merge with PAT |
| `.opencode/commands/agentic-task-machine-quality-check.md` | Quality command: review all merged PRs + comments → pass/fail |
| `tests/sim/__init__.py` | Simulation core — copy verbatim |
| `tests/sim/models.py` | Simulation core — copy verbatim |
| `tests/sim/agents.py` | Simulation core — copy verbatim |
| `tests/sim/engine.py` | Simulation core — copy verbatim |
| `tests/agentic_task_machine/__init__.py` | Empty init |
| `tests/agentic_task_machine/agents.py` | Adapted simulation agents for agentic-task-machine |
| `tests/test_agentic_task_machine_state_machine.py` | pytest state machine tests |
| `pyproject.toml` | uv project with pytest dev dep |
| `Makefile.ghprj` | Label bootstrap (`type/user`, `type/task`, `blocked`) |

## Existing Files to Modify

_None — this is a new system._

## Labels to Create

| Label | Color | Description |
|-------|-------|-------------|
| `type/user` | `0075ca` | User-facing feature request |
| `type/task` | `e4e669` | Implementation sub-task |
| `blocked` | `d93f0b` | Blocked — requires human intervention |

## Manual Post-Install Steps

1. GitHub Settings → Actions → Workflow permissions → Read and write
2. GitHub Settings → Actions → Allow GitHub Actions to create and approve pull requests
3. Add secret `AGENT_GH_TOKEN` with `repo` scope (integrator push to protected branch)
4. Branch protection on `main`: require at least 1 approving review

## Deferred (out of scope for this run)

- `DEFINITION_OF_DONE.md` — quality agent relies on the original `type/user` issue acceptance criteria instead

---

## Step-by-Step Tasks

Execute in order. Each task is atomic and independently verifiable.

### CREATE `.github/workflows/core-opencode-run.yml`

- **SOURCE**: `.github/skills/agentic-workflow-system/assets/examples/core-opencode-run.yml`
- **ACTION**: Copy verbatim — no changes required
- **VALIDATE**: `actionlint -shellcheck= .github/workflows/core-opencode-run.yml`

### CREATE `.github/workflows/core-state-heal.yml`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/core-state-heal.yml`
- **PATTERN**: Replace example state list with `["blocked"]` in all THREE places: `fromJSON([...])`, `STATE_LABELS`, `--argjson states`
- **GOTCHA**: Missing any one of the three locations causes label conflicts to go undetected
- **VALIDATE**: `grep -c '"blocked"' .github/workflows/core-state-heal.yml` → must return 3

### CREATE `.github/config/config.yml`

- **CONTENT**: `model: opencode/big-pickle`, `max_wip: 5`
- **VALIDATE**: `yq '.model' .github/config/config.yml | grep -v '^null$'`

### CREATE `.github/workflows/sm-user.yml`

- **MIRROR**: `sm-workflow-template.yml` three-phase structure
- **TRIGGER**: `issues: [opened]` + schedule every 6h
  - `opened`: fires for every new issue; prepare auto-labels non-bot issues as `type/user`
    (`github.event.issue.user.type != 'Bot'` guard) — this is the primary entry point
- **AUTO-LABEL STEP**: when `event.action == 'opened'`, `gh issue edit --add-label "type/user"`
  runs before "Find candidates" so the issue is classified before any planning logic
- **PREPARE idempotency**: check if any `type/task` issues exist referencing `#N` (open or closed) — skip if found
- **SIGNAL**: sub-issue existence check (no comment signal); fallback → `blocked` on parent issue
- **PROXY**: none
- **RUNNER**: `ubuntu-latest`
- **VALIDATE**: `actionlint -shellcheck= .github/workflows/sm-user.yml`

### CREATE `.github/workflows/sm-task.yml`

- **MIRROR**: `sm-workflow-template.yml` three-phase structure
- **TRIGGER**: `issues: labeled` with `type/task` + `issues: unlabeled` with `blocked` + schedule every 6h
- **PREPARE idempotency**: check if issue is open, has `type/task`, NOT `blocked`; check if linked open PR exists (`Closes #N` in any open PR) — skip if found
- **SIGNAL**: `<!-- PR-CREATED -->`; fallback → `blocked`
- **PROXY**: none
- **RUNNER**: `ubuntu-latest`
- **VALIDATE**: `actionlint -shellcheck= .github/workflows/sm-task.yml`

### CREATE `.github/workflows/agent-integrator.yml`

- **MIRROR**: `agent-workflow-template.yml`
- **TRIGGER**: `pull_request_review: submitted` (type `approved`) only
- **PREPARE**: fetch the approved PR; pass context to agent
- **SECRET**: uses `AGENT_GH_TOKEN` (not `GITHUB_TOKEN`) for merge step
- **PROXY**: none
- **RUNNER**: `ubuntu-latest`
- **VALIDATE**: `actionlint -shellcheck= .github/workflows/agent-integrator.yml`

### CREATE `.github/workflows/agent-quality.yml`

- **MIRROR**: `agent-workflow-template.yml`
- **TRIGGER**: `issues: closed` + schedule every 6h
- **PREPARE**: if `issues: closed` event, check issue has `type/task`; find `Parent issue: #N`; check all sibling `type/task` issues are closed and parent is still open; skip if not all closed or parent already closed
- **SIGNAL**: `<!-- QUALITY-PASSED -->` or `<!-- QUALITY-FAILED -->`
- **VERIFY**: if QUALITY-PASSED → close parent `type/user`; if QUALITY-FAILED → new `type/task` sub-issues created by agent; if no signal → post comment + exit 0 (retry on schedule)
- **PROXY**: none
- **RUNNER**: `ubuntu-latest`
- **VALIDATE**: `actionlint -shellcheck= .github/workflows/agent-quality.yml`

### CREATE `.opencode/agent/planner.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/agents/planner.md`
- **OUTPUT CONTRACT**: creates `type/task` sub-issues with `Parent issue: #N` in body; posts a plain summary comment (no signal marker needed)
- **VALIDATE**: `grep -q "^description:" .opencode/agent/planner.md || echo FAIL`

### CREATE `.opencode/agent/worker.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/agents/dev.md`
- **OUTPUT CONTRACT**: PR body MUST contain `Closes #N`; comment `<!-- PR-CREATED -->` on issue after PR is opened + approved
- **VALIDATE**: `grep -q "^description:" .opencode/agent/worker.md || echo FAIL`

### CREATE `.opencode/agent/integrator.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/agents/integrator.md`
- **DIFF**: uses `AGENT_GH_TOKEN`; ensures CI passes before merging (fix CI if failing)
- **VALIDATE**: `grep -q "^description:" .opencode/agent/integrator.md || echo FAIL`

### CREATE `.opencode/agent/quality.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/agents/review.md`
- **OUTPUT CONTRACT**: comment `<!-- QUALITY-PASSED -->` or `<!-- QUALITY-FAILED -->` on parent `type/user` issue
- **VALIDATE**: `grep -q "^description:" .opencode/agent/quality.md || echo FAIL`

### CREATE `.opencode/commands/agentic-task-machine-plan-user-issue.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/commands/ghaw-plan-issue.md`
- **PATTERN**: create N `type/task` issues each with `Parent issue: #N` and implementation plan; post a plain summary comment on parent
- **VALIDATE**: `grep -q "^argument-hint:" .opencode/commands/agentic-task-machine-plan-user-issue.md || echo FAIL`

### CREATE `.opencode/commands/agentic-task-machine-work-task-issue.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/commands/ghaw-dev-issue.md`
- **PATTERN**: create branch → implement → open PR (`Closes #N`) → self-review comment → `gh pr review --approve` → post `<!-- PR-CREATED -->` on issue
- **VALIDATE**: `grep -q "^argument-hint:" .opencode/commands/agentic-task-machine-work-task-issue.md || echo FAIL`

### CREATE `.opencode/commands/agentic-task-machine-integrate.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/commands/ghaw-integrate.md`
- **DIFF**: single-PR focus (not batch); uses `AGENT_GH_TOKEN` env var; ensures CI passes first (fix if not)
- **VALIDATE**: `grep -q "^argument-hint:" .opencode/commands/agentic-task-machine-integrate.md || echo FAIL`

### CREATE `.opencode/commands/agentic-task-machine-quality-check.md`

- **MIRROR**: `.github/skills/agentic-workflow-system/assets/examples/commands/ghaw-review.md` (if present)
- **PATTERN**: read parent `type/user` issue; read all closed `type/task` sub-issues; read merged PR diffs; judge sufficiency; post `<!-- QUALITY-PASSED -->` or `<!-- QUALITY-FAILED -->` + new sub-issues if failed
- **VALIDATE**: `grep -q "^argument-hint:" .opencode/commands/agentic-task-machine-quality-check.md || echo FAIL`

### CREATE simulation test layer

- **COPY verbatim**: `tests/sim/__init__.py`, `tests/sim/models.py`, `tests/sim/agents.py`, `tests/sim/engine.py`
- **ADAPT**: `tests/agentic_task_machine/agents.py` — four agent subclasses: Planner, Worker, Integrator, Quality
- **ADAPT**: `tests/test_agentic_task_machine_state_machine.py` — happy path + no-output + idempotency per agent
- **ADAPT**: `pyproject.toml` — project name `agentic-task-machine-sim`
- **VALIDATE**: `uv run pytest tests/test_agentic_task_machine_state_machine.py`

### CREATE `Makefile.ghprj`

- **CONTENT**: `setup-labels` target creating `type/user`, `type/task`, `blocked` via `gh api`
- **VALIDATE**: dry-run with `--dry-run` or manual inspection

---

## Validation Commands

Run after all files are created. Zero failures required before committing.

```bash
# Lint
yamllint .github/workflows/*.yml .github/config/config.yml
actionlint -shellcheck= .github/workflows/*.yml

# Structural checks
for f in .github/workflows/sm-*.yml; do
  grep -q "^  prepare:" "$f" && grep -q "^  run:" "$f" && grep -q "^  verify:" "$f" \
    || echo "FAIL: $f missing a phase"
done

# State healer sync — must return 3
grep -c '"blocked"' .github/workflows/core-state-heal.yml

# Signal coverage
for CMD in .opencode/commands/*.md; do
  grep -oP '<!-- [A-Z-]+ -->' "$CMD" | while read SIG; do
    MARKER=$(echo "$SIG" | tr -d '<>! -')
    grep -rl "$MARKER" .github/workflows/ || echo "WARNING: $SIG from $CMD not found in workflows"
  done
done

# Simulation tests
uv sync && uv run pytest tests/test_agentic_task_machine_state_machine.py
```
