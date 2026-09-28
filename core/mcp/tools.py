from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Awaitable

from core.types import GenerationRequest, MediaKind, GeneratedMedia


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str                     # для системного промпта LLM
    args_hint: str                       # человекочитаемая шпаргалка аргументов


# Каталог инструментов MCP. Расширение = новый ToolSpec + регистрация в registry,
# не правки в текст-сервисе (Open/Closed).
ToolSpecs = {
    "generate_image": ToolSpec(
        name="generate_image",
        description="Generate an image from a prompt. Returns image bytes.",
        args_hint="prompt: str, style: optional str",
    ),
    "edit_image": ToolSpec(
        name="edit_image",
        description="Edit an image with a text instruction.",
        args_hint="prompt: str, image: bytes",
    ),
    "enhance_prompt": ToolSpec(
        name="enhance_prompt",
        description="Improve a prompt with the text model, art-director style.",
        args_hint="prompt: str",
    ),
}


@dataclass(slots=True)
class ToolContext:
    """Всё, что инструменту нужно для исполнения. Собирается вызывающим слоем."""
    user_id: int
    chat_id: int | None
    locale: str
    request_factory: Callable[..., GenerationRequest]


class ToolRegistry:
    """Регистрируем callable-инструменты; LLM-слой описывает их в промпте."""

    def __init__(self):
        self._tools: dict[str, Callable[[ToolContext, dict], Awaitable[object]]] = {}

    def register(self, name: str, fn: Callable[[ToolContext, dict], Awaitable[object]]) -> None:
        if name not in ToolSpecs:
            raise ValueError(f"unknown tool spec: {name}")
        self._tools[name] = fn

    def system_prompt_block(self) -> str:
        lines = ["You can call tools:"]
        for spec in ToolSpecs.values():
            lines.append(f"- {spec.name}: {spec.description} ({spec.args_hint})")
        lines.append("Call a tool by responding with: TOOL <name> {json-args}")
        return "\n".join(lines)

    async def dispatch(self, ctx: ToolContext, name: str, args: dict) -> object:
        fn = self._tools.get(name)
        if fn is None:
            raise KeyError(f"tool not registered: {name}")
        return await fn(ctx, args)
