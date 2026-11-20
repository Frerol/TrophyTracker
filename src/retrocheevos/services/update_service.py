"""Is there a newer release on GitHub than the one running?

Notify-only by design: this reads a public endpoint and returns a version and
a URL. It never downloads, never writes to disk, never touches the running
install. Anything more would need to deal with signing, permissions on
Program Files, and replacing a running .exe — all of which is a different
problem from telling someone a new version exists.

Plain synchronous Python with no Qt imports, like the rest of `services/`
(see `sync_service.py`) — `gui/` runs it on a `ServiceWorker` thread, because
a network call on the UI thread would freeze the window at startup, which is
the one moment the app can least afford it.

Not authenticated, and must stay that way: the endpoint is public, and the
API key this app already holds is a RetroAchievements key that has no
business being sent to GitHub.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests

from retrocheevos.version import APP_VERSION, GITHUB_OWNER, GITHUB_REPO

logger = logging.getLogger(__name__)

LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# Short on purpose. This runs during startup; if GitHub is slow the right
# outcome is "no banner", not a worker thread hanging around for the default
# timeout while the user is already using the app.
REQUEST_TIMEOUT_SECONDS = 5

# GitHub serves this unauthenticated, but asks for a User-Agent and will
# reject requests without one.
REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"TrophyTracker/{APP_VERSION}",
}

_VERSION_PART = re.compile(r"\d+")


@dataclass(frozen=True)
class AvailableUpdate:
    version: str
    url: str


def parse_version(raw: str) -> Optional[tuple[int, ...]]:
    """`"v1.2.3"` -> `(1, 2, 3)`. None if there are no numbers in it at all.

    Tuples, **not** string comparison: `"1.10.0" < "1.9.0"` is true for
    strings and false for versions, so a lexical compare would go quiet at
    exactly the tenth release and stay quiet.

    Anything trailing the numbers (`v1.2.3-beta`, `1.2.3 (hotfix)`) is
    ignored rather than rejected — a release named slightly off shouldn't
    disable the check.
    """
    parts = _VERSION_PART.findall(raw or "")
    if not parts:
        return None
    return tuple(int(part) for part in parts)


def is_newer(candidate: str, current: str) -> bool:
    """Is `candidate` a later version than `current`?

    Unparseable on either side means False. "Can't tell" has to read as "no
    update" — the alternative is a banner that can't be made to go away by
    updating, which is worse than a missed release.

    Different lengths are padded, so 1.2 vs 1.2.0 compares equal rather than
    the shorter one losing.
    """
    candidate_parts = parse_version(candidate)
    current_parts = parse_version(current)
    if candidate_parts is None or current_parts is None:
        return False
    length = max(len(candidate_parts), len(current_parts))
    padded_candidate = candidate_parts + (0,) * (length - len(candidate_parts))
    padded_current = current_parts + (0,) * (length - len(current_parts))
    return padded_candidate > padded_current


def should_notify(available_version: str, dismissed_version: Optional[str]) -> bool:
    """Has this update already been dismissed?

    Kept separate from `check_for_update` and free of any storage access so
    it can be reasoned about on its own: the caller supplies whatever it read
    from preferences, including None.

    The bias here is the opposite of `is_newer`'s. There, "can't tell" means
    no banner, because a banner you can't clear is worse than a missed
    release. Here, "can't tell" means *show it* — a dismissal nobody can
    interpret must not silence the check permanently, which is the failure
    mode you'd never notice, because its symptom is nothing happening.
    """
    if not dismissed_version:
        return True
    # Exact tag match first, so a dismissal is honoured even for a tag with
    # no parseable number in it at all.
    if available_version.strip() == dismissed_version.strip():
        return False
    if parse_version(dismissed_version) is None:
        return True
    return is_newer(available_version, dismissed_version)


def check_for_update(current_version: str = APP_VERSION) -> Optional[AvailableUpdate]:
    """The latest published release, if it's newer than what's running.

    Returns None for every kind of "no" there is — up to date, no releases
    published yet, offline, GitHub down, rate limited, malformed response.
    The caller cannot distinguish them, and shouldn't: an update check that
    interrupts someone because their wifi is off is a bug, not a feature. The
    reason is logged, not shown.

    `/releases/latest` rather than `/releases` because it already excludes
    drafts and pre-releases, so an unfinished tag can't advertise itself.
    """
    if not GITHUB_OWNER or not GITHUB_REPO:
        return None

    try:
        response = requests.get(
            LATEST_RELEASE_URL,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        # 404 is the normal answer for a repo with no releases published yet,
        # not an error worth a warning.
        if response.status_code == 404:
            logger.info("Update check: no releases published yet")
            return None
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        logger.info("Update check skipped: %s", error)
        return None
    except ValueError as error:  # JSON that isn't JSON, e.g. a captive portal
        logger.info("Update check got a non-JSON response: %s", error)
        return None

    if not isinstance(payload, dict):
        logger.info("Update check got an unexpected payload type")
        return None

    tag = payload.get("tag_name") or payload.get("name") or ""
    if not is_newer(tag, current_version):
        return None

    # Falls back to the releases page rather than giving up: `html_url` is
    # always present in practice, but the banner is useless without somewhere
    # to send the user, and the releases page is always a valid destination.
    url = payload.get("html_url") or RELEASES_PAGE_URL
    logger.info("Update available: %s (running %s)", tag, current_version)
    return AvailableUpdate(version=tag, url=url)
