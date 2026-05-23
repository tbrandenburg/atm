---
description: Review the complete solution for a type/user issue and post a quality signal
argument-hint: <quality-context-json>
---

# Quality Check

**Input**: $ARGUMENTS (JSON map of parent issue numbers to their context:
parent issue data, closed type/task sub-issues, and merged PR diffs)

## Step 1: Parse Context

Read the full input. For each parent issue number:
- `parent_issue`: the `type/user` issue (number, title, body, acceptance criteria)
- `tasks`: array of closed `type/task` sub-issues with their comments
- `pull_requests`: map of task number → merged PRs with diff previews

## Step 2: Review Each Parent Issue

For each parent issue in the context:

### 2a: Extract Acceptance Criteria

Read the parent `type/user` issue body and identify all acceptance criteria
(explicitly stated or implied by the description).

### 2b: Map Criteria to Implementation

For each acceptance criterion:
1. Find which `type/task` sub-issue(s) address it
2. Find the corresponding merged PR and review its diff
3. Verify the criterion is actually satisfied in the implementation

### 2c: Assess Quality

Check the overall implementation for:
- Correctness: does it do what was asked?
- Completeness: are all criteria addressed?
- Test coverage: are there meaningful tests?
- Code quality: no obvious bugs, no TODO-for-prod, no dead code?

## Step 3: Write Signal Files

Do NOT use `gh issue comment` or `gh issue create`. The verify step reads files from `gh-artifacts/`
and handles all GitHub interactions atomically.

### If ALL criteria are met (sufficient):

    mkdir -p gh-artifacts
    cat > gh-artifacts/quality-result.md <<'EOF'
    signal: QUALITY-PASSED

    <!-- QUALITY-PASSED -->
    ✅ Quality review passed.

    **Acceptance criteria review:**
    - [x] {criterion 1} — addressed in #{task} via PR #{pr}
    - [x] {criterion 2} — addressed in #{task} via PR #{pr}

    All criteria satisfied. Solution is complete and sufficient.
    EOF

### If ANY criteria are NOT met (insufficient):

Write one file per gap, then the failure signal (file naming and format are defined in your
agent instructions):

    mkdir -p gh-artifacts/tasks
    cat > gh-artifacts/tasks/{parent_number}-gap-1-{slug}.md <<'EOF'
    title: {gap title}

    Parent issue: #{parent_number}

    ## Context
    Follow-up from quality review of parent issue #{parent_number}.

    ## Gap
    {specific, actionable description of what is missing or incorrect}

    ## Acceptance Criterion Not Met
    {quote the criterion from the parent issue}

    ## Implementation Plan

    ### Approach
    {concrete approach to address the gap}

    ### Steps
    1. {step}
    2. {step}

    ### Estimated Complexity
    {low/medium/high}
    EOF

    cat > gh-artifacts/quality-result.md <<'EOF'
    signal: QUALITY-FAILED

    <!-- QUALITY-FAILED -->
    ❌ Quality review found gaps.

    **Unmet criteria:**
    - [ ] {criterion} — {specific gap description}

    Follow-up tasks will be created automatically.
    EOF
