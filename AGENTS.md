# agentic-task-machine - Agent Instructions

## Deployment

This project runs on **github.com** using standard GitHub-hosted runners.

Use current public GitHub Actions versions such as `actions/upload-artifact@v4` and `actions/download-artifact@v4`.

## Using `gh` CLI in workflows

All `gh` commands target github.com by default. Workflows should provide a token through `GH_TOKEN` and should not set `GH_HOST` or pass `--hostname`.

## Non-Interactive Execution

Agents in this repository run **non-interactively** inside GitHub Actions. There is no human at the keyboard to respond to prompts. Any operation that would pause and wait for user input will hang the workflow until it times out.

- Do not use tools or commands that prompt for confirmation (e.g. `--interactive`, password prompts, `read` calls).
- Pass all required values as arguments or environment variables upfront.
- Prefer flags like `--yes`, `--force`, `--non-interactive`, or `-y` where available to suppress prompts.
- If a tool has no non-interactive mode, find an alternative or pre-configure it via config files.
- Always use timeouts for bash calls (e.g. `timeout 60 <command>`) to prevent hung processes from blocking the workflow indefinitely.
