# Project documentation

All project documentation must be written in English. This includes README
files, changelogs, technical documentation, roadmaps, archived handoffs,
release notes, generated release metadata, and documentation distributed with
release artifacts. Apply this rule when creating or updating documentation.

Keep code identifiers, filenames, URLs, and proper names unchanged. Original
visual reference assets may retain their source-language artwork; describe
them in English in the surrounding documentation.

Conversation with the user may follow the user's preferred language.

# Changelog and release notes

`CHANGELOG.md` is the running source for the next release description. Its
top section, `## Unreleased`, collects every change made since the latest
published release.

While working after a release:

- When a change affects users, packaging, dependencies, compatibility, data,
  or the release process, add a bullet to `## Unreleased` in the same commit
  as the change. Purely internal edits (typos, comment tweaks, refactors with
  no observable effect) do not need an entry.
- Write each entry in English, as one concise line in the imperative mood
  (for example, "Fix ...", "Add ...", "Require ..."), describing the effect
  rather than the implementation.
- Update or remove an existing `Unreleased` entry when a later change revises
  or reverts it, so the section always reflects the net result relative to the
  last release.
- Mark changes that need user action (data migrations, changed settings,
  removed features, new system requirements) explicitly so they can be called
  out in the release description.
- Never edit the sections of versions that were already published, except to
  fix factual errors.

When preparing a release:

1. Rename `## Unreleased` to `## <version> — <YYYY-MM-DD>` and start a new,
   empty `## Unreleased` section above it.
2. Use that section as the basis for `packaging/RELEASE-<version>.txt`,
   following the structure of the previous release notes (download and
   verification steps, compatibility, changes, validation). Group and reword
   the entries for end users where needed, but do not add changes that are not
   recorded in the changelog.
3. Update `packaging/README.md` if it refers to a specific release notes file.
