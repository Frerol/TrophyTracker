# Documentation

Start with the [desktop roadmap](planning/DevelopmentRoadmap.md) for current
priorities and the proposed interface revamp. The HTML reference is a design
artifact; its screens are not yet implemented in the application.

## Technical reference

- [Architecture and repository layout](Architecture.md)
- [Coding standards](CodingStandards.md)
- [Database schema and recovery](Database.md)
- [API usage](API.md)

## Planning

- [Desktop development roadmap](planning/DevelopmentRoadmap.md)
- [Android roadmap](planning/AndroidRoadmap.md)
- [Product vision](planning/Vision.md)
- [Future ideas](planning/FutureIdeas.md)

## Design

- [UI specification](design/UI.md)
- [Current branding and artwork history](design/Branding.md)
- [Proposed UI: Dashboard, Library, Game detail and Brand](design/ui-proposal.html)
- [Historical Home preview](design/previews/home-1.1.0.png)

The proposal was originally supplied as
“RetroAchievements Tracker — Proposta de UI.html”. It is kept as
`docs/design/ui-proposal.html` for a stable, portable filename. The roadmap
records the proposed A/C brand options; the runtime artwork remains under
`assets/` until the brand implementation is selected and delivered.

## Validation and history

- [R05–R10 performance and resilience evidence](validation/PerformanceValidation.md)
- [Historical implementation handoff](archive/HANDOFF.md)

Development commands live in the [project README](../README.md). Build inputs
live in [`packaging/`](../packaging/README.md); developer utilities and optional
third-party binaries live in [`tools/`](../tools/README.md). Generated builds,
local databases, logs and caches are not documentation or source assets.
