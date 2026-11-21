# TrophyTracker — Future Ideas

Unscheduled ideas, not committed to any version. See
`DevelopmentRoadmap.md` for the active plan; the original version buckets in
`../archive/RoadmapHistory.md` are not current release commitments.

## Product ideas

- Steam Deck support
- Plugin system
- Themes
- Cloud Sync
- Achievements timeline
- Game comparison
- Friend comparison
- Advanced recommendations
- Leaderboards (RetroAchievements, friends, daily/weekly/all time)
- Start TrophyTracker at login, hidden in the tray (builds on R28)
- System notification when an unlock is detected (builds on R30's local
  signals; must state when the unlock is not yet confirmed by
  RetroAchievements)

## Cut from the UI proposal review

These appeared in the supplied UI proposal and were removed by the
[product fit review](../design/ProposalReview.md) because the application has
no data source or product scope for them yet. Reviving one requires its own
data contract before it enters the roadmap (decision D5).

- Ranking and global totals
- Achievement rarity and rarity sorting
- Game release year and year sorting
- Near-mastery highlights
- Achievement RetroPoints, author/dates and global recent unlocks
- Instant achievement-unlock notifications (requires gameplay or event
  monitoring)
- Publishing comments or replies from the application

## Guiding Rule

Same test as everything else in the project (`Vision.md`):

> "If RetroAchievements released an official desktop application, would this
> feature belong here?"

Only promote an idea from this list into `DevelopmentRoadmap.md` once
there's a clear yes and the data it needs is available.
