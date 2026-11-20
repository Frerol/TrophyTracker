"""The installed version, and the tag it corresponds to on GitHub.

This is the single source of truth. `services/update_service.py` compares it
against the latest GitHub release; nothing else should hardcode a version.

Bumping a release:
  1. Raise APP_VERSION here.
  2. Commit, then tag it `v<APP_VERSION>` and push the tag.
  3. Publish a GitHub release for that tag.

Step 3 is the one that matters — `update_service` reads *releases*, not tags,
so a pushed tag with no release published against it is invisible to the
check. That is deliberate: it lets a tag exist before the build is ready to
hand out.
"""

APP_VERSION = "1.1.0"

GITHUB_OWNER = "Gmendes223"
GITHUB_REPO = "Retrocheevos"
