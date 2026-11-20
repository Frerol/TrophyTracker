# R05–R10 performance and resilience validation

Measured on 2026-11-20 with the project's `.venv` (Python 3.14, SQLite 3.54.0),
using Qt's offscreen platform on the development machine. Results are local
observations, not performance guarantees for other hardware.

Reproduce from the repository root:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/benchmarks/benchmark_explorer.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

The benchmark creates an isolated temporary database with 13,327 games, hashes
and account completion records. All covers are mocked: there is no network
access or use of personal account data. It exercises a full-catalog search,
model replacement, sorting and viewport repaint in a visible offscreen table.

## R05: indexed hash matching

494 successful lookups spread through the hash table took 730.47 ms with the
previous `LOWER(hash) = LOWER(?)` query and 2.48 ms with the normalized equality
lookup (about 294 times faster in this run). `EXPLAIN QUERY PLAN` reports:

```text
SEARCH game_hashes USING INDEX idx_game_hashes_hash (hash=?)
```

A miss still uses the compatibility scan, intentionally preserving legacy
mixed-case rows. Tests cover normalized writes, uppercase inputs, raw uppercase
legacy rows, misses, v23 migration and a successful lookup that never executes
the fallback. The schema comment now correctly describes SQLite's index rules.

## R06: Explorer refresh

The first probe, with the initial debounce implementation but the original
Qt sorting proxy, measured 1,343.53 ms median and 1,970.06 ms maximum across
five full refreshes. A four-keystroke burst took 1,505.04 ms from input to
render, including the debounce delay. Each refresh executed eight SELECTs.
Profiling showed roughly 1.2 million calls to the Python model's `data()` across
six refreshes: repeated Qt sort comparisons dominated model replacement.

The final implementation sorts DTOs once per row key in the table model and
samples at most 100 rows when sizing content columns. Search, filter and
explicit refresh reads run through a registered service worker. Each page
allows one read in flight and retains only the latest queued request. Results
are checked against the request generation, current account and pending input
before they can replace the model. Reads use one SQLite transaction for games,
progress, catalog count and account-scoped installed IDs; Core still owns the
filter rules.

Final measurements:

| Metric | Result |
| --- | ---: |
| Full refresh through rendered viewport, median of five | 135.61 ms |
| Full refresh, maximum | 148.61 ms |
| Four-keystroke burst, input to render, including 150 ms debounce | 270.16 ms |
| SELECTs per full refresh | 7 |
| SELECTs for a four-keystroke burst | 7 |
| Maximum gap in a 5 ms GUI heartbeat during the probe | 72.72 ms |

Without debounce the original Home path would execute four refreshes, or 32
SELECTs for the same four input changes. The final path executes one refresh.
The worker keeps database reading off the GUI thread; sorting and rendering
still run on the GUI thread and account for residual event-loop delay. These
measurements favor a worker and cheaper sorting over introducing SQL filtering
rules or pagination at this catalog size.

Tests cover both page instances, Enter avoiding a duplicate timer refresh,
coalescing while a read is held, rejection of stale results/account changes,
blocked and completed exclusions, list membership, installed filtering and
account isolation. Numeric sorting, unknown values, descending order,
persistent selection and preservation of sort order on refresh are covered.

## R07: artwork cache

Downloads use unique temporary files in the destination directory and publish
with `os.replace`; a failed write or replace removes the temporary file and
preserves any existing final file. Game artwork orchestration shares in-flight
results across page loaders, including callers requesting matched-ROM artwork.
The shared entry is removed in a `finally` block, so exceptions allow retries.

Successful thumbnails use an LRU cache with a 4 MiB pixel budget per Explorer
model. After browsing 13,327 synthetic covers, measured retained pixels were
4,194,304 bytes. With 32 × 32, 32-bit thumbnails, this permits 1,024 thumbnails
per model; two Explorer instances permit 8 MiB total retained thumbnail pixels.
This budget excludes Python/Qt object overhead, source images in flight and
on-disk files; it is not a process RSS limit. Failure metadata is independently
bounded to 1,024 entries per model. Pending IDs are tracked separately so
thumbnail eviction cannot lose an in-flight request marker.

Failures expire after 30 seconds. A model-owned timer invalidates expired rows,
so visible covers can recover after connectivity returns without another user
action. Revisited rows can also retry after their deadline. Tests inject a
failed replace, concurrent writers, shared concurrent lookups, worker exceptions,
retry after failure, automatic repaint after expiry and long browsing beyond
both cache limits.

## R08: partial activity feeds and incremental rendering

`get_recent_activity_feed` now returns `ActivityFeedResult`: sorted `entries`,
`failed_usernames`, `following_unavailable` and a derived `partial` flag.
A failed summary is logged and skipped while remaining users continue; a
failed optional progress lookup retains its summary and marks the result
partial. Authentication, rate-limit and cancellation errors propagate instead
of being mistaken for an unavailable individual. A missing follow list can
still return the current user's activity with an explicit diagnostic.

Home merges last-good cards for unavailable users, retaining cached progress
when the failed progress request refers to the same game. A partial update is
visibly labeled and backs off; a complete success restores the base interval.
Global failures preserve the cached feed. Rendering is keyed by username and
only replaces changed cards: the test streams 31 entries, verifies that the
first card survives every addition, then verifies reuse during reordering and
replacement when its content changes. Existing account/generation guards and
refresh pacing remain in place.

## R09: streaming folder discovery

`library/rom_traversal.py` walks using a stack of live `os.scandir` iterators,
without sorting or materializing the tree. Traversal memory and open directory
handles scale with nesting depth rather than total entries. Named exclusions
come from the existing `SKIPPED_DIR_NAMES` policy and apply below the configured
root. Hidden directories remain traversable; directory symlinks are not followed.
Unreadable descendants are reported without discarding readable siblings.

The scan callback reports `(discovered_entries, current_path)`, including
directories and rejected files, beginning at the root before enumeration. Both
Library scan actions forward this through a dedicated `(int, str)` worker
signal. GUI notifications are throttled to avoid queueing one event per file.
Cancellation is checked during discovery and closes outstanding iterators.
Completed per-ROM database writes survive cancellation as before.

A synthetic enumeration probe on 2026-11-20 consumed 1,000 and 100,000 virtual
file entries using the production iterator. Both delivered the first file after
pulling exactly one entry. `tracemalloc` peaks were 9,882 and 3,342 bytes,
respectively, with all iterators closed. This measures traversal allocations,
not filesystem caches, hashing buffers, installed-ROM lookup data or the
accumulated scan result. Unit tests reproduce the early-yield behavior with
100,000 entries and test pruning, hidden directories, supported suffixes,
symlink cycles, errors, cancellation and progress delivery.

## R10: completed empty metadata responses

Migration v28 adds `game_metadata_fetches`, independently tracking hash and
median-time outcomes. A successful empty response suppresses another request
for 30 days. Failed responses remain immediately retryable; expired empty
responses are offered again, and `force_refresh=True` on either backfill
bypasses freshness for all browsable games. Historical populated values keep
the previous complete-on-backfill behavior. Installed-game prioritization is
preserved.

Outcome markers and values commit together. Cancellation creates no success
marker, failed forced requests preserve old values, and `NULL` duration is
never replaced by zero just to indicate a completed fetch. Both the lightweight
hash backfill and full-details path record successful empty responses.

The ten metadata-backfill regression tests cover immediate repeats, request
failures, forced failures, expiration and its exact boundary, independent
metadata clocks, real zero durations, cancellation, rollback, prioritization,
full-details fetching and upgrading an existing v27 database.

Final R08–R10 validation: **286 tests passed** with the full offscreen unittest
command above, using temporary fixtures and mocked API responses; no live API
calls or migration of the user's working database were needed.
