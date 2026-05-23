---
description: Implement a type/task issue atomically: branch, implement, PR, self-review, approve
argument-hint: <issue-number-or-json>
---

# Work Task Issue

**Input**: $ARGUMENTS (issue number OR JSON with issue data from batch mode)

## For Each Candidate Issue

### Step 1: Read Issue

    gh issue view {number} --json number,title,body,labels,comments

Extract:
- Parent issue number from `Parent issue: #N` in body
- Implementation plan (approach, affected components, concrete steps)
- Acceptance criteria

### Step 2: Check Idempotency

Verify no open PR already exists for this issue:

    gh pr list \
      --state open \
      --json number,body \
      --jq "[.[] | select(.body | test(\"[Cc]loses #${NUMBER}\"))] | length"

If count > 0, skip this issue — it already has a PR in progress.

### Step 3: Determine Branch Name

Determine the branch name using your branch naming convention.

### Step 4: Create Branch

    git fetch origin
    git checkout -b {branch-name} origin/main
    # OR if branch already exists (e.g. previous partial run):
    git checkout {branch-name}

### Step 5: Explore and Implement

Use file-read tools to explore affected components (guided by implementation plan).
Implement changes following existing patterns and conventions.
Do NOT introduce new dependencies without a strong reason.

### Step 6: Write Tests

Write or update unit tests for changed components.
Follow existing test structure — no new test frameworks.

### Step 7: Commit and Push

    git add -A
    git commit -m "{type}({scope}): {description} (closes #{N})"
    git push origin {branch-name}

### Step 8: Open Pull Request

    gh pr create \
      --title "{type}({scope}): {description}" \
      --body "## Summary

    {brief description of what changed and why}

    ## Changes
    - {change 1}
    - {change 2}

    Closes #{N}" \
      --head {branch-name} \
      --base main

The body MUST contain the exact string `Closes #{N}` — this is how the verify step
confirms the PR exists and how GitHub closes the issue on merge.

**IMPORTANT**: `{N}` is the **GitHub issue number** (a plain integer, e.g. `Closes #42`).
Never use agentic-task-machine internal notation such as `{parent}-{subtask}` (e.g. `#21-1` is wrong
because GitHub will parse it as `#21` and auto-close the parent issue on merge).
The PR body must close **only the task issue**. Never add a `Closes` reference to the
parent `type/user` issue — closing the parent is the quality agent's decision.

### Step 9: Self-Review

Read through the full diff of the PR:

    gh pr diff {pr_number}

Verify against each acceptance criterion. Check:
- [ ] All acceptance criteria from the issue are addressed
- [ ] Code follows existing conventions
- [ ] Tests cover the changed code
- [ ] No debug code, no TODO-for-prod, no secrets in code

Post a self-review comment:

    gh pr review {pr_number} \
      --comment \
      --body "## Self-Review

    **Acceptance criteria:**
    - [x/- ] {criterion} — {comment}

    **Test coverage:** {what was added or updated}

    **Code quality:** {brief assessment}

    **Ready for merge:** yes / no — {if no, what needs fixing}"

### Step 10: Signal Ready for Merge

If the self-review found no blockers, add the `status/ready-to-merge` label to signal
the integrator agent (GitHub forbids PR authors from approving their own PR, so a label
is used as the readiness signal instead):

    gh pr edit {pr_number} --add-label "status/approved"

### Step 11: Handle Blockers

If a blocker is discovered at ANY step that prevents completing the task:

    gh issue edit {N} --add-label "blocked"
    gh issue comment {N} \
      --body "🚧 Blocked during implementation: {specific reason}.
      Human intervention required."

Stop immediately. Do NOT create a PR for a blocked issue.
