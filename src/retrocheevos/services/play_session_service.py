"""Account-scoped local emulator sessions, shared by all launch entry points."""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Optional


@dataclass
class PlaySession:
    game_id: Optional[int]
    title: str
    process: subprocess.Popen
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_sessions: dict[Optional[int], PlaySession] = {}
_lock = Lock()


def record_launch(account_id: Optional[int], game_id: Optional[int], title: str, process: subprocess.Popen) -> None:
    with _lock:
        _sessions[account_id] = PlaySession(game_id, title, process)


def get_running_session(account_id: int) -> Optional[PlaySession]:
    with _lock:
        session = _sessions.get(account_id)
        if session is not None and session.process.poll() is not None:
            _sessions.pop(account_id, None)
            return None
        return session
