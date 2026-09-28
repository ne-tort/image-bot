# MCP: text AI as orchestrator

## Idea

The text model is not just a chat feature — it can *call* other core
capabilities. Registered tools:

| Tool | Description |
|---|---|
| `generate_image` | Text → image via ImageService |
| `edit_image` | Image + instruction → new image |
| `enhance_prompt` | Art-director prompt rewriting |

## Flow

```
user text ─▶ TextService (system prompt + tool catalog)
        ◀─ "TOOL generate_image {"prompt": ...}"
             └─▶ ToolRegistry.dispatch(ctx, name, args)
                     └─▶ ImageService.generate(...)
```

## Extension (Open/Closed)

1. Add a `ToolSpec` to `ToolSpecs`.
2. Register the callable in `CoreContainer._register_tools`.
No changes in TextService or tgbot.

## Current status

v0.1 ships the registry, specs, and the `enhance_prompt` wiring used by the
✨ button. Full LLM-loop dispatch (multi-turn tool use) is a roadmap item.
