# Roadmap completion audit — 2026-11-20

## Conclusion

The blanket statement that R01–R15 are complete is too strong. Ten items have
implementation and supporting local evidence; five need follow-up: R01, R02,
R03, R04 and R11. This audit does not modify application code or count passing
tests as proof of scenarios the tests do not exercise.

“Supported” below means code inspection and the available local checks support
the claim within the stated scope, not exhaustive validation on every platform.

## Checks executed

On Linux, using the existing `.venv` (Python 3.14), from the repository root:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/benchmarks/benchmark_explorer.py
```

- Full suite: **298 tests passed** in 5.537 seconds.
- Indexed hash lookup: 494 lookups, 707.71 ms with the old query versus 2.38 ms
  with normalized equality; the query plan uses `idx_game_hashes_hash`.
- Explorer: 13,327 rows; median refresh 129.64 ms, maximum 162.96 ms;
  four-keystroke burst 283.50 ms and seven SELECTs; maximum heartbeat gap 78.66 ms.
- Artwork: retained thumbnail pixels reached, but did not exceed, 4,194,304 bytes
  per model. This is not a total process-memory or disk-cache measurement.
- Two additional isolated probes reproduced the R01 and R04 findings below.
  They used a bare Home state with a simulated occupied worker registry and a
  temporary SQLite database built by the existing rehash test fixture.

No live API, user database or real credential vault was used. No new Windows,
release-package, hosted CI or framework-upgrade run was performed.

## Item-by-item assessment

| Item | Assessment | Evidence / remaining work |
| --- | --- | --- |
| R01: reject stale account results | Partial; reproduced refresh gap | Account/generation guards exist, but a previous account's worker can defer the new account's fetch. Dedicated Home account-switch regression coverage is absent. |
| R02: cancellation and shutdown | Partial; incomplete validation and cancellation path | Registry, cooperative cancellation and image-loader shutdown exist. Tests cover a synthetic cooperative worker and an idle image loader, not closing during every real operation or a delayed API request. Shared API pacing still uses an uninterruptible wait. |
| R03: global sync coordination | Partial; bypass found in code | Explorer, Settings and Library acquire job tokens; Home's opportunistic profile sync does not. Shared pacing and bounded sync retries exist, but conflict/429 regression scenarios are not covered by dedicated tests. |
| R04: changed ROM detection | Partial; reproduced stale match | Rescan fingerprints, manual-match preservation, forced rehash and GUI artwork invalidation exist. Forced rehash retains an obsolete automatic match when the new hash has no catalog match. |
| R05: indexed hash lookup | Supported | Hash-case tests pass; rerun benchmark confirms indexed equality and the speed improvement. |
| R06: Explorer refresh | Supported | Background snapshots, debounce/coalescing, account guards, filter semantics and sorting have passing coverage; benchmark reproduces the documented improvement. |
| R07: artwork caching | Supported within documented cache scope | Atomic-publication, single-flight, exception/retry and bounded model-cache tests pass; pixel budget reproduced. |
| R08: partial activity/rendering | Supported | Per-user failure handling, authentication/rate-limit propagation, last-good merging and card-reuse tests pass. |
| R09: streaming discovery | Supported | Traversal and scan-progress tests pass, including early yield, exclusions, cancellation, errors and discovery before hashing. |
| R10: empty metadata fetches | Supported | Backfill tests pass for empty success, expiry, retries, forced failures, cancellation, transaction rollback and v27 upgrade. |
| R11: reproducible checks/platform validation | Infrastructure implemented; validation incomplete | Workflow, locks, smoke probe and GUI regressions exist. Native Windows and hosted CI execution are not established by this audit; existing documentation explicitly leaves native Windows validation pending. |
| R12: roadmap reconciliation | Supported | Current modules/navigation and removed features are distinguished from the historical sections; Android is explicitly separate. The new completion findings must be considered alongside the previous blanket status. |
| R13: migration/backup recovery | Supported for tested schemas | Atomic migration, failed initialization, backup/restore, WAL restore and export-redaction tests pass. Populated upgrade/restore coverage starts at v26; it does not establish every historical upgrade path. |
| R14: vault/database consistency | Supported with simulated vault failures | Account-recovery tests pass for SQL/commit/vault failures, durable fallback, deferred deletion and re-added accounts. Real OS-vault integration was not exercised. |
| R15: launch recency | Supported with simulated processes | Launch-recovery tests pass for process creation failure, metadata failure before launch, successful recency updates and persistence failure after creation. |

## Findings requiring follow-up

### R01 — an occupied old worker consumes the new account's refresh interval

In `gui/pages/home_page.py`, `_on_active_account_changed` cancels the old work
and resets freshness, but `_refresh_activity_feed` then sets
`_activity_last_attempt` **before** checking `workers.has_key(HOME_WORKER_ACTIVITY)`.
The registry retains the cancelled worker until it actually finishes. If B
refreshes during that interval, no B request starts, but the attempt is recorded.
There is no queued B request attached to the old worker's completion.

The isolated probe called the production method with account B active and the
activity worker slot occupied. At monotonic time 1000, the method set
`_activity_last_attempt` to 1000 and returned; `_activity_refresh_is_due` was
false. Automatic retry can consequently wait for the three-minute interval;
explicit later refresh/navigation may start it sooner. The probe establishes
the method-level gap, not a real-network account-switch reproduction.

Follow-up: queue/retry the current account after the old request finishes, avoid
stamping a request that never started, and test delayed partial/final/error/photo
callbacks across A → B and logout using controlled workers.

### R02 — shutdown evidence does not cover the promised operation matrix

`api/client.py::RequestPacer.wait` sleeps while holding its lock and accepts no
cancellation callback. A server-directed penalty can reach 120 seconds, even
though the worker registry's shutdown wait is five seconds. This contradicts
the assumption that only one ten-second HTTP request can outlive cancellation.
Home's opportunistic profile worker also does not pass cooperative cancellation.

The registry retains lingering workers, but the suite does not prove safe
process exit with a delayed pacer/request or active image download. This audit
does not claim a reproduced native crash.

Follow-up: make shared pacing cancellation-aware, propagate cancellation to
Home profile work, and validate closing during sync, scan, activity and image
work, including tasks that exceed the shutdown budget and committed progress.

### R03 — Home profile sync bypasses the global job slot

`gui/pages/home_page.py::refresh` starts
`ServiceWorker(sync_service.sync_profile_if_needed, client, account)` guarded
only by `HOME_WORKER_PROFILE_SYNC`. It never acquires a `job_coordinator` token.
When stale, that service calls `sync_profile` and writes profile data. Settings
can independently acquire `JOB_SYNC_PROFILE` and start the same kind of work.
Shared HTTP pacing limits request rate but does not make these jobs exclusive.

Follow-up: include Home's conditional sync in coordination and test simultaneous
Home/Explorer/Settings triggers, token release and bounded mocked-429 recovery.

### R04 — forced verification keeps a match for the old file

In `services/library_service.py::rehash_installed_roms`, automatic matches are
updated only when `game_id is not None`. If replacement bytes hash to an unknown
game, the new hash is saved while the old `game_id` survives. The normal changed-
file rescan handles this case differently by allowing `set_game_id(..., None)`.

The temporary-database probe created game 1 with the old hash, installed an
automatically matched ROM, then mocked hashing to return a new unknown hash.
After forced rehash, the new hash was stored but `game_id` remained 1 and
`manual_match` was false. The existing test
`test_an_existing_match_is_never_cleared` explicitly preserves this older
behavior, contrary to the current service docstring's automatic-match policy.

Follow-up: clear obsolete automatic matches on a changed unknown hash while
preserving manual matches; align the regression test with the intended policy.
Add specific fingerprint/rescan/manual-preservation coverage.

### R11 — distinguish configured CI from executed platform checks

`.github/workflows/ci.yml` configures Linux/Windows tests, packaging smoke runs
and an upgrade probe. Configuration alone does not prove those jobs passed.
`Testing.md` says hosted CI has not been run in the documented session and that
Windows results were obtained under Wine; native Windows remains pending.
The current local run also uses Python 3.14, outside the configured 3.12/3.13
matrix. It supplements rather than replaces those checks.

Follow-up: obtain native Windows suite/package/upgrade evidence and executed
CI-matrix results before declaring the full R11 acceptance criteria verified.

## Follow-up — 2026-11-20

The R01–R04 findings above were addressed in the working tree after this audit.
R11 remains open. Original findings are kept unchanged above as the record of
what was observed before the fixes.

| Item | Change | Regression coverage |
| --- | --- | --- |
| R01 | `_refresh_activity_feed` no longer stamps `_activity_last_attempt` for a request that never started. When the occupied activity slot belongs to an earlier account generation, a retry is queued and started as soon as that worker finishes. A fetch already running for the current account does not queue a duplicate. The photo worker key is scoped to the account generation. Saved accounts no longer switch the displayed account implicitly; selecting a removed account reports an error instead of logging out. | `tests/gui/test_home_account_workers.py` (A → B and logout with delayed partial/final/error/photo callbacks, immediate retry, no duplicate same-account fetch); `tests/gui/test_account_selection.py`. |
| R02 | `RequestPacer.wait` sleeps outside its lock in short slices and honours the worker's cancellation through a context-local `cancellation_scope`, so a 120-second penalty no longer blocks shutdown or other callers. Home profile sync is cancellable. Closing the window requests cancellation without blocking the event loop and retries until workers and image loaders drain, bounded by `SHUTDOWN_TIMEOUT_MS`; work still running after the budget stays referenced and the close proceeds. | `tests/api/test_request_pacing.py`; `tests/gui/test_lifecycle_regression.py` (close during API penalty, image download, sync, scan and activity; clean child-process exit; close after the shutdown budget with a non-cooperative worker). |
| R03 | Home's opportunistic profile sync acquires the `JOB_SYNC_PROFILE` token, releases it when the worker finishes or when setup fails, and does not start while another job holds the slot. | `tests/gui/test_home_account_workers.py` (Home/Settings/both Explorers share one slot; release on setup failure); bounded 429 retry and cancellation during backoff in `tests/api/test_request_pacing.py`. |
| R04 | Forced rehash clears an obsolete automatic match when the replacement bytes hash to an unknown game; manual matches are still preserved. | `tests/services/test_rehash_installed_roms.py` (policy updated); `tests/services/test_wii_rvz_scan.py`. |

Check executed on Linux with the existing `.venv` (Python 3.14):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .
```

Result: **323 tests passed**. The two regressions added last (bounded close and
no duplicate same-account activity fetch) were confirmed to fail with their
fixes reverted. No live API, user database or real credential vault was used.

### R11 — hosted CI evidence (2026-11-20)

The repository was published to GitHub and `.github/workflows/ci.yml` ran on
hosted runners for the first time.

- The first runs (commits `2fc6963` and `c17b7ed`) failed on `windows-latest`:
  tests built paths from unresolved temporary directories, which Windows
  reports as 8.3 short paths (`C:\Users\RUNNER~1\...`), while the
  application stores resolved long paths. The Explorer debounce test also used
  a fixed 220 ms sleep that was too short on the Windows Python 3.12 runner.
  Both were test defects, fixed in `tests/` by resolving temporary roots and
  polling with a deadline; no application change was required.
- Run `44840664571` (commit `baf3079`) passed every blocking job: the full
  suite (323 tests) on Linux and Windows × Python 3.12/3.13, and packaging
  smoke builds that start the frozen bundle on Linux and Windows.
- The non-blocking dependency-upgrade probe installed PySide6 6.12.0 over the
  6.10.1 release pin. All 78 GUI regressions passed, but the process crashed
  during interpreter teardown on both platforms (Linux: `Bus error` after
  `QObject: shared QObject was deleted directly`; Windows: exit code 127). The
  PySide6 pin therefore stays at 6.10.1; the probe should be re-run before any
  upgrade.

Remaining for R11: interactive use of the application on a native Windows
desktop (real display, not the offscreen platform) has not been exercised.
Hosted runners provide native Windows for the automated suite and packaged
startup only.
