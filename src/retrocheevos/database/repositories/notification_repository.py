"""Data access for `notifications` (Database.md 5.1).

`notification_settings` went with migration v22 — nothing ever read or wrote
it, and the three methods here that touched it had no callers.
"""

import sqlite3

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.notification import Notification
from retrocheevos.utils.enums import NotificationType


class NotificationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, notification: Notification) -> Notification:
        cursor = self._connection.execute(
            """
            INSERT INTO notifications (account_id, type, game_id, message, created_at, read)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                notification.account_id,
                notification.type.value,
                notification.game_id,
                notification.message,
                datetime_to_sql(notification.created_at),
                notification.read,
            ),
        )
        notification.id = cursor.lastrowid
        return notification

    def list_for_account(self, account_id: int, unread_only: bool = False) -> list[Notification]:
        query = "SELECT * FROM notifications WHERE account_id = ?"
        params: list = [account_id]
        if unread_only:
            query += " AND read = 0"
        query += " ORDER BY created_at DESC"
        rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_notification(row) for row in rows]

    def mark_read(self, notification_id: int) -> None:
        self._connection.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))

    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> Notification:
        return Notification(
            id=row["id"],
            account_id=row["account_id"],
            type=NotificationType(row["type"]),
            game_id=row["game_id"],
            message=row["message"],
            created_at=datetime_from_sql(row["created_at"]),
            read=bool(row["read"]),
        )
