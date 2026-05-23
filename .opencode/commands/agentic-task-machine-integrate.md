---
description: Ensure CI passes and merge an approved pull request to main using a PAT
argument-hint: <pr-context-json>
---

# Integrate Pull Request

**Input**: $ARGUMENTS (JSON with PR data, changed files, diff preview, and main SHA)

## Step 1: Parse PR Context

Read the full input. Extract:
- PR number, title, branch name
- Review decision and merge state status
- CI check results (statusCheckRollup)
- Changed files and diff preview

## Step 2: Pre-Merge Eligibility Check

    gh pr view {pr} --json reviewDecision,mergeStateStatus,reviews,statusCheckRollup

Check for `CHANGES_REQUESTED` reviews:

    gh pr view {pr} --json reviews \
      --jq '[.reviews[] | select(.state == "CHANGES_REQUESTED")] | length'

If any `CHANGES_REQUESTED` reviews exist:

    gh pr comment {pr} \
      --body "⏸️ Integrator deferred: PR has outstanding CHANGES_REQUESTED review.
      Resolve the review before this PR can be merged."

Stop — do not merge.

## Step 3: Update Branch if Behind or Dirty

If `mergeStateStatus` is `BEHIND` or `DIRTY`:

    git fetch origin
    git checkout {branch}
    git rebase origin/main
    git push --force-with-lease origin {branch}

Wait a moment for GitHub to process the push before checking CI.

## Step 4: Ensure CI is Green

Check current CI status:

    gh pr view {pr} --json statusCheckRollup \
      --jq '.statusCheckRollup[] | select(.conclusion == "FAILURE" or .conclusion == "TIMED_OUT")'

If failures exist:

### 4a: Diagnose

    # Get the failing run ID
    gh run list --branch {branch} --json databaseId,status,conclusion,name --jq '.[] | select(.conclusion == "failure")'
    gh run view {run_id} --log-failed | head -200

### 4b: Fix

Based on the failure logs, apply the minimal fix (typo in test, import error, formatting, etc.)

    git add -A
    git commit -m "fix: resolve CI failure ({brief description})"
    git push origin {branch}

### 4c: Wait for CI

After pushing the fix, check CI again. Repeat steps 4a–4c if CI still fails (max 3 attempts).

If after 3 attempts CI still fails:

    # Extract the linked issue number from the PR body (Closes #N)
    ISSUE_NUM=$(gh pr view {pr} --json body --jq '.body' | grep -oP '(?<=Closes #)\d+' | head -1)

    gh pr comment {pr} \
      --body "⏸️ Integrator could not resolve CI failure after 3 attempts.
      Marking issue #${ISSUE_NUM} as blocked for human triage.
      Last failure:
      {summary of last error}"

    # Signal blockage on the linked task issue so the worker can be re-triggered
    # once the root cause is resolved
    gh issue edit ${ISSUE_NUM} --add-label "blocked"

Stop — do not merge.

## Step 5: Merge

Merge the PR (the `GH_TOKEN` already in the environment is the agent PAT that can
push to branch-protected main):

    gh pr merge {pr} \
      --merge \
      --delete-branch

GitHub will automatically close the linked issue via `Closes #N` in the PR body.

## Step 6: Post-Merge Verification

    git checkout main && git pull
    echo "Main now at: $(git rev-parse HEAD)"

If the merge caused an obvious structural issue (missing file, broken import):

    gh pr comment {pr} \
      --body "⚠️ Post-merge check detected a potential issue: {description}.
      Please verify main branch is stable."

## Step 7: Summary

Print a brief summary to stdout confirming what was done:

    echo "Integrator summary:"
    echo "  Merged: PR #{pr} — {title}"
    echo "  Branch: {branch} → main"
    echo "  CI fixes applied: {count}"
