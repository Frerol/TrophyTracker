# TrophyTracker — Coding Standards

## Development Rules

- Small modules.
- Single responsibility.
- Type hints everywhere.
- PEP8 compliant.
- No duplicated code.
- No magic values.
- Logging throughout.
- Proper error handling.
- Background threads for long operations — **never freeze the UI**.

## Threading Model

- All network calls (API) and heavy I/O (ROM scanning/hashing) must run on
  background threads/workers — **never on the UI thread**.
- GUI must remain responsive at all times; long operations report progress
  back via signals/callbacks handled by Services.

## Layering Rule

- **GUI must never communicate directly with the API.**
- Everything goes through `Services` → `Core`.
- See `Architecture.md` for the full layer breakdown.

## Language & Naming

- Everything in English: UI text, variables, classes, functions, comments,
  documentation.
- No magic values — use named constants / enums (e.g. list types, game
  types, notification types).

## Testing & Quality

- Tests live in `tests/`, mirroring the `src/retrocheevos/` module structure.
- No feature is "done" until it has error handling and logging around any
  network or filesystem interaction.

## Working with Claude Code

- Never invent architecture — follow `Architecture.md`, `Database.md`,
  `API.md`, and `UI.md`.
- Always follow the existing project folder structure (`Architecture.md`
  §3).
- Implement module by module, smallest reasonable unit at a time; review
  before moving to the next module.
