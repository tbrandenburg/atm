# Pi CLI

This repo configures Pi via `.pi/settings.json` and `.pi/extensions/opencode-zen.ts` to use the keyless `opencode` provider with the `big-pickle` model.

Run a prompt non-interactively from the repo root:

```bash
pi --no-session --no-tools -p "Reply with exactly: dummy ok"
```

Keep extensions enabled. Passing `--no-extensions` disables `.pi/extensions/opencode-zen.ts` and falls back to the built-in `opencode` provider, which requires `OPENCODE_API_KEY`.
