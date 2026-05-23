---
description: Break a type/user issue into parallelisable type/task sub-issues with implementation plans
argument-hint: <issue-number-or-json>
---

# Plan User Issue

**Input**: $ARGUMENTS (issue number OR JSON with issue data from batch mode)

## Step 1: Parse Input

If $ARGUMENTS is a plain integer, it is a single issue number:

    gh issue view $ARGUMENTS --json number,title,body,labels,comments

If $ARGUMENTS is JSON, it may contain one or more issues — process each in turn.

Extract for each issue: number, title, body, acceptance criteria (if stated).

## Step 2: Read the Sandbox Section

Read `README.md` and locate the Sandbox section. Extract the current emoji in each of
the 12 `<td>` cells (4 rows × 3 columns). Record them as a grid:

    row 1: [cell1, cell2, cell3]
    row 2: [cell1, cell2, cell3]
    row 3: [cell1, cell2, cell3]
    row 4: [cell1, cell2, cell3]

Also note the theme hinted by the user issue title/body — this is the only thing the
issue content is used for.

## Step 3: Check if Already Planned

Before creating sub-issues, verify no GitHub sub-issues already exist for this parent:

    gh api --paginate \
      "repos/{owner}/{repo}/issues/${ISSUE_NUMBER}/sub_issues?per_page=100" \
      --jq '.[]' | jq -s length

If count > 0, this issue is already planned — skip it and log a note.

## Step 4: Decompose into Sub-tasks (Sandbox Only)

**Always create exactly 9 sub-tasks** — one per cell of the Sandbox table, addressed
left-to-right, top-to-bottom (row 1 col 1 … row 4 col 3 — pick any 9 of the 12 cells,
or all 12 if you prefer, but 9 is the minimum).

For each sub-task:
- Pick a replacement emoji inspired by the theme derived in Step 2.
- The emoji must differ from the current one in that cell.
- Title format: `Replace Sandbox cell R{row}C{col} emoji`
- Affected component: `README.md` — Sandbox section `<td>` at row {row}, column {col}
- The implementation step is simply: edit that single `<td>` line to swap the emoji.

> **Scope lock**: no other files, sections, or lines may be mentioned or touched.

## Step 5: Write Sub-task Files

Write one file per sub-task. File naming and format are defined in your agent instructions.

    mkdir -p gh-artifacts/tasks
    cat > gh-artifacts/tasks/{parent_number}-1-{slug}.md <<'EOF'
    title: {sub-task title}

    ## Context
    {which part of the parent feature this covers}

    ## Implementation Plan

    ### Approach
    {1-2 sentences}

    ### Affected Components
    - `{file}` — {reason}

    ### Steps
    1. {step}
    2. {step}

    ### Risks / Unknowns
    - {risk}

    ### Estimated Complexity
    {low/medium/high} — {justification}
    EOF

Repeat for each sub-task, incrementing the counter (`-1-`, `-2-`, …).
