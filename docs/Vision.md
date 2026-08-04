# RetroCheevos — Vision

## Project Name

**RetroCheevos**
Tagline: *The ultimate desktop companion for RetroAchievements.*

## Project Goal

RetroCheevos is **not** a RetroAchievements scraper. It is intended to become
the desktop application that RetroAchievements should have had.

Focus areas:

- Speed
- Clean UI
- Automation
- Performance
- Organization
- Offline cache
- Windows-first (future Linux & Steam Deck support)

The application should feel like a **native desktop application**, not a
website.

## Philosophy

Every feature must answer this question:

> "If RetroAchievements released an official Windows application, would this
> feature belong here?"

- If yes → implement.
- If not → reject.

The application must always stay:

- Clean
- Compact
- Fast
- Professional

## Language Standard

Everything must be in English:

- UI
- Variables
- Classes
- Functions
- Comments
- Documentation

## Development Principle

The project must always prioritize, in this order:

1. Performance
2. Stability
3. Clean Architecture
4. Maintainability
5. User Experience

Never sacrifice performance for unnecessary visual effects.

## Development Workflow

- **ChatGPT** (original planning): architecture, product design, UX,
  brainstorming, technical decisions.
- **Claude Code** (implementation): implementation, refactoring, testing,
  module creation.

Rules for Claude Code:

- Never invent architecture.
- Always follow the documentation.
- Always follow the project structure.

See `Architecture.md`, `Database.md`, `API.md`, `UI.md`, `CodingStandards.md`
and `DevelopmentRoadmap.md` for implementation-level detail, and
`FutureIdeas.md` for out-of-scope ideas.
