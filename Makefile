.PHONY: update-skills

update-skills:
	npx ai-agent-skills install https://github.com/tbrandenburg/ghaw-sandbox/tree/main/.github/skills/agentic-workflow-system --agent vscode
