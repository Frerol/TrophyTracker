"""In-app notifications — the service layer over `NotificationRepository`.

The tables, model and repository have existed since the first migration but
had no caller; this is the layer that connects them to the GUI, following
the same GUI -> service -> repository shape as the rest of the app. Only
new-event alerts use it today (`sync_service.sync_event_progress` detects
them, Home's Events section shows them).
"""

from datetime import datetime

from retrocheevos.database.connection import get_connection
from retrocheevos.database.repositories.notification_repository import (
    NotificationRepository,
)
from retrocheevos.models.notification import Notification
from retrocheevos.utils.enums import NotificationType


def record_new_events(account_id: int, events: list[tuple[int, str]]) -> int:
    """Stores one unread notification per newly-appeared event, skipping any
    already recorded. Returns how many were actually added.

    The dedupe matters because `NotificationRepository.add` is a plain
    INSERT: a sync interrupted after the catalog phase but before this one
    would otherwise re-report the same events on the next run.
    """
    if not events:
        return 0

    with get_connection() as connection:
        repository = NotificationRepository(connection)
        already_notified = {
            notification.game_id
            for notification in repository.list_for_account(account_id)
            if notification.type == NotificationType.EVENT
        }
        added = 0
        for game_id, title in events:
            if game_id in already_notified:
                continue
            repository.add(
                Notification(
                    account_id=account_id,
                    type=NotificationType.EVENT,
                    game_id=game_id,
                    message=title,
                    created_at=datetime.now(),
                )
            )
            added += 1
    return added


def list_unread_events(account_id: int) -> list[Notification]:
    with get_connection() as connection:
        return [
            notification
            for notification in NotificationRepository(connection).list_for_account(
                account_id, unread_only=True
            )
            if notification.type == NotificationType.EVENT
        ]


def mark_events_read(account_id: int) -> None:
    with get_connection() as connection:
        repository = NotificationRepository(connection)
        for notification in repository.list_for_account(account_id, unread_only=True):
            if notification.type == NotificationType.EVENT and notification.id is not None:
                repository.mark_read(notification.id)
