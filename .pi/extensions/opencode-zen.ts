import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.registerProvider("opencode", {
    baseUrl: "https://opencode.ai/zen/v1",
    api: "openai-completions",
    apiKey: " ",
    headers: { "Authorization": "Bearer " },
    compat: {
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
    },
    models: [
      {
        id: "big-pickle",
        name: "Big Pickle (DeepSeek V4 Flash)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 128000,
        maxTokens: 16384,
      },
    ],
  });
}
