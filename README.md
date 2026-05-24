# agentic-task-machine

A fully autonomous, GitHub Actions–driven issue-resolution system. Human-created feature requests are broken down into parallelisable sub-tasks, implemented end-to-end by LLM agents, and validated for quality — all without human intervention unless an agent is explicitly blocked.

## Installation

Install ATM into another GitHub repository from that repository root:

```bash
curl -fsSL https://raw.githubusercontent.com/tbrandenburg/atm/main/Makefile.ghprj | make -f - install
```

Force overwrite existing ATM files:

```bash
curl -fsSL https://raw.githubusercontent.com/tbrandenburg/atm/main/Makefile.ghprj | make -f - install-force
```

The installer copies the GitHub workflows, OpenCode agents, OpenCode commands, and the bundled agentic workflow skill. It also sets `AGENT_GH_TOKEN` from the current `gh` authentication token and runs `setup-labels`, which creates or updates the required labels idempotently.

Commit and push the installed files:

```bash
git add .github .opencode .atm-version && git commit -m "feat: Add ATM agentic workflow"
git push
```

Before installation, authenticate `gh` with a token that can create repository secrets and labels. After installation, enable GitHub Actions workflow write permissions and PR approval permissions.

## How it works

| State | Entry condition | Agent | Core action | Exit condition |
|---|---|---|---|---|
| **New user issue** | Issue opened by a human — `type/user` label auto-applied | Planner | Break into parallelisable `type/task` sub-issues | `type/task` sub-issues exist with GitHub sub-issue relations to parent |
| **New task issue** | Issue labeled `type/task` _or_ `blocked` removed | Worker | Create branch → implement → open PR → self-review + approve | Linked open PR exists |
| **Merge** | PR approved by worker self-review | Integrator | Ensure CI is green → merge to `main` → close `type/task` issue | PR merged, issue closed |
| **Quality check** | All `type/task` for a `type/user` are closed | Quality | Review merged PRs; judge sufficiency | Sufficient → close `type/user`; insufficient → new `type/task` issues |

## Inputs and outputs

**Inputs:** GitHub issues opened by humans. No special format required — the planner agent handles breakdown.

**Outputs:**
- `type/task` sub-issues with implementation plans
- Feature branches and pull requests per sub-task
- Merged commits to `main`
- Closed `type/user` issues on quality confirmation

## Labels

| Label | Meaning |
|---|---|
| `type/user` | Human-authored feature request; auto-applied on issue open |
| `type/task` | Implementation sub-task created by the planner |
| `blocked` | Worker failed; human removes label to retry |

## Sandbox

Here is the agentic-task-machine sandbox:

<table>
  <tr>
    <td>🧪</td>
    <td>📝</td>
    <td>⛈️</td>
  </tr>
  <tr>
    <td>🔬</td>
    <td>🌪️</td>
    <td>📋</td>
  </tr>
  <tr>
    <td>🎯</td>
    <td>❄️</td>
    <td>🏆</td>
  </tr>
</table>
