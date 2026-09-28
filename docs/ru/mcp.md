# MCP: текстовый ИИ как оркестратор

## Идея

Текстовая модель — не только чат. Она умеет **вызывать** другие способности
ядра. Зарегистрированные инструменты:

| Инструмент | Что делает |
|---|---|
| `generate_image` | Текст → картинка через ImageService |
| `edit_image` | Картинка + инструкция → новая картинка |
| `enhance_prompt` | Перезапись промпта «арт-директором» |

## Поток

```
текст юзера ─▶ TextService (системный промпт + каталог инструментов)
          ◀─ "TOOL generate_image {\"prompt\": ...}"
               └─▶ ToolRegistry.dispatch(ctx, name, args)
                       └─▶ ImageService.generate(...)
```

## Расширение (Open/Closed)

1. Добавить `ToolSpec` в `ToolSpecs`.
2. Зарегистрировать callable в `CoreContainer._register_tools`.
Без правок TextService и tgbot.

## Текущее состояние

v0.1 содержит реестр, спеки и подключение `enhance_prompt` для кнопки ✨.
Полный LLM-цикл (multi-turn tool use) — в roadmap.
