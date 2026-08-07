"""Aggregates raw per-game completion progress into `ProfileStats`.

`api/profile.py`'s `RawGameProgress.highest_award_kind` is RetroAchievements'
own classification, confirmed against `API_GetUserCompletionProgress.php` —
no need to derive Beaten/Mastered from a completion percentage.

- Beaten: any award at all — `beaten-hardcore`, `beaten-softcore`,
  `completed` or `mastered`. `highest_award_kind` is the *highest* award,
  so a game you went on to master no longer reports "beaten"; counting only
  the two beaten values therefore undercounted badly (46 mastered games
  were missing from the total). Mastering a game necessarily means beating
  it, which is why RA's own site counts it that way.
- Mastered: `highest_award_kind` is `mastered` (always hardcore, by RA's own
  definition). A subset of the beaten count, not disjoint from it.
- `completion_percentage` matches the site's **"Average completion"** field:
  the *unweighted mean* of each game's `num_awarded / max_possible`, over the
  games on the Completion Progress page, **excluding subsets**.

  This was settled by measurement, not reasoning — both earlier formulas were
  wrong and the two mistakes pulled in opposite directions:

  | Formula | Value | Site |
  |---|---|---|
  | Unweighted mean, 1st page only (original) | 63.12 % | 56.75 % |
  | `sum(awarded) / sum(possible)` (weighted) | 42.21 % | 56.75 % |
  | Unweighted mean, all 147 games | 56.37 % | 56.75 % |
  | **Unweighted mean, all games minus subsets** | **56.75 %** | 56.75 % |

  So the unweighted mean was right all along; what made it read high was the
  missing pagination (`api/profile.py`), and switching to a weighted ratio to
  compensate replaced one error with a bigger one. The remaining 0.38 pp gap
  was a single row: `Dragon Ball Z: Budokai [Subset - Martial Arts
  Tournament]` at 1.43 %. Dropping it gives 56.7470 → 56.75, and it matches
  how `database/repositories/game_repository.py::_BROWSABLE_GAME_CLAUSES`
  already treats subsets everywhere else.

  Two things this account could not distinguish, left as notes rather than
  guesses: it has 0 softcore points, so `NumAwarded` and `NumAwardedHardcore`
  are identical on every row and either could be the field RA uses; and it has
  no event/standalone games (console 101/102), so whether RA also drops those
  is untested — only the subset exclusion is evidence-backed, so only that one
  is applied.
"""

from retrocheevos.api.profile import RawAwardKind, RawGameProgress, RawUserProfile
from retrocheevos.models.profile import ProfileStats

# Every award implies the game was beaten — see the module docstring.
BEATEN_AWARD_KINDS = {
    RawAwardKind.BEATEN_HARDCORE,
    RawAwardKind.BEATEN_SOFTCORE,
    RawAwardKind.COMPLETED,
    RawAwardKind.MASTERED,
}

# RA names subsets "<Game> [Subset - <name>]". Same marker the catalog
# queries use, kept as a literal here because this list comes from the API
# and never touches SQL.
SUBSET_TITLE_MARKER = "[Subset -"


def build_profile_stats(
    account_id: int,
    profile: RawUserProfile,
    completion_progress: list[RawGameProgress],
) -> ProfileStats:
    games_beaten = sum(
        1 for game in completion_progress if game.highest_award_kind in BEATEN_AWARD_KINDS
    )
    games_mastered = sum(
        1 for game in completion_progress if game.highest_award_kind == RawAwardKind.MASTERED
    )
    completion_percentage = _average_completion(completion_progress)

    return ProfileStats(
        account_id=account_id,
        points=profile.points,
        hardcore_points=profile.hardcore_points,
        games_beaten=games_beaten,
        games_mastered=games_mastered,
        completion_percentage=completion_percentage,
        true_points=profile.true_points,
        user_pic_path=profile.user_pic_path,
    )


def _average_completion(completion_progress: list[RawGameProgress]) -> float:
    """The site's "Average completion" — see the module docstring for the
    measurements that pinned this down.

    Note the games are *not* excluded from `games_beaten`/`games_mastered`:
    those two are already confirmed against the site at 98/56, and this
    account's only subset carries no award, so excluding it there would be a
    guess that changes nothing. If a subset ever does earn an award and the
    counts drift from the site, this is the place to revisit.
    """
    per_game = [
        game.num_awarded / game.max_possible
        for game in completion_progress
        if game.max_possible
        and game.num_awarded is not None
        and SUBSET_TITLE_MARKER not in game.title
    ]
    if not per_game:
        return 0.0
    return 100 * sum(per_game) / len(per_game)
