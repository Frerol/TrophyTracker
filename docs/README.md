# Documentation

Start with the [desktop roadmap](planning/DevelopmentRoadmap.md) for current
priorities and the proposed interface revamp. The reviewed HTML is a design
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
- [Reviewed UI proposal: eight desktop boards](design/ui-proposal-reviewed.html)
- [Product fit review and implementation mapping](design/ProposalReview.md)
- [Screen, action and data mapping (R16)](design/ScreenDataMapping.md)
- [Original supplied UI proposal: six boards](design/ui-proposal.html)
- [Historical Home preview](design/previews/home-1.1.0.png)

The supplied UI proposal is preserved as
`docs/design/ui-proposal.html` for a stable, portable filename. The reviewed copy corrects scope and adds
Explorer/Lists without overwriting the source. The roadmap
records the proposed A/C brand options; the runtime artwork remains under
`assets/` until the brand implementation is selected and delivered.

## Validation and history

- [Roadmap completion audit and follow-up](validation/RoadmapCompletionAudit.md)
- [Testing, CI and dependency policy](validation/Testing.md)
- [R05–R10 performance and resilience evidence](validation/PerformanceValidation.md)
- [Roadmap history: R01–R15 review and earlier plans](archive/RoadmapHistory.md)
- [Historical implementation handoff](archive/HANDOFF.md)

Development commands live in the [project README](../README.md). Build inputs
live in [`packaging/`](../packaging/README.md); developer utilities and optional
third-party binaries live in [`tools/`](../tools/README.md). Generated builds,
local databases, logs and caches are not documentation or source assets.
