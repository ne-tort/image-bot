# Telegram UX

## Private chat

- Plain text → image. No /command required (PromptArt pattern).
- Photo + caption → edit.
- Under every result: ✨ Make it better / Again.
- Inline keyboards only. Reply keyboards never (they hijack the user's
  keyboard and are ignored in groups).
- Status message «Рисую…» → deleted on success; error replaces it.

## Groups

Golden rules (learned from capslock/Eugene references):

1. **Explicit triggers only**: `/gen`, `/edit` (reply to a photo), @mention,
   or reply to the bot. Never react to arbitrary messages.
2. **Privacy Mode must be OFF** (BotFather) or the bot sees none of this.
   Documented in deployment.md.
3. `my_chat_member`: added → friendly hello + auto-enable; removed →
   mark chat disabled. No wall of text.
4. Admin gates: `/enable`, `/disable` are admin-only.
5. Per-chat daily ceiling (GROUP_DAILY_LIMIT) so one group can't starve
   everyone.

## Error copy

Every failure mode has a human message (core/i18n/messages.py):

| Case | Tone |
|---|---|
| Own daily limit | «Лимит на сегодня исчерпан 🌙 …» — honest, tells when it resets |
| Own hourly limit | «Полегче 🚀 …» — playful, short |
| Provider 429 | blame ourselves, give a retry time |
| Content filter | suggest rewording, no moralizing |
| Provider down | invite to retry in a minute |

Never: raw exceptions, error codes, "Something went wrong".
