# TrophyTracker — Vision

## Project Name

**TrophyTracker**
Tagline: *The ultimate desktop companion for RetroAchievements.*

## Project Goal

TrophyTracker is **not** a RetroAchievements scraper. It is intended to become
the desktop application that RetroAchievements should have had.

Focus areas:

- Speed
- Clean UI
- Automation
- Performance
- Organization
- Offline cache
- Cross-platform desktop: Linux releases today, Windows after native
  validation, Steam Deck as a future idea

The application should feel like a **native desktop application**, not a
website.

## Philosophy

Every feature must answer this question:

> "If RetroAchievements released an official desktop application, would this
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

The project was originally planned with ChatGPT and implemented with Claude
Code. Current practice:

- Product, design and scope decisions are made by the maintainer and recorded
  in the documentation (`DevelopmentRoadmap.md`, `ProposalReview.md`).
- AI agents implement, refactor, test and document changes, following
  `AGENTS.md`.

Rules for implementation agents:

- Never invent architecture; follow the documented project structure.
- Follow the documentation, and update it in the same change when behavior
  changes.
- Leave open product decisions to the maintainer (see the roadmap's open
  decisions) instead of choosing silently.

See `Architecture.md`, `Database.md`, `API.md`, `UI.md`, `CodingStandards.md`
and `DevelopmentRoadmap.md` for implementation-level detail, and
`FutureIdeas.md` for out-of-scope ideas.
