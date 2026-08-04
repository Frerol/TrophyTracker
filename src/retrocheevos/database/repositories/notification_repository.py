"""Data access for `notifications` and `notification_settings` (Database.md 5.1, 5.2)."""

import sqlite3
from typing import Optional

from retrocheevos.database.serialization import datetime_from_sql, datetime_to_sql
from retrocheevos.models.notification import Notification, NotificationSetting
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

    def get_setting(self, account_id: int, notification_type: NotificationType) -> Optional[bool]:
        row = self._connection.execute(
            "SELECT enabled FROM notification_settings WHERE account_id = ? AND type = ?",
            (account_id, notification_type.value),
        ).fetchone()
        return bool(row["enabled"]) if row else None

    def set_setting(
        self, account_id: int, notification_type: NotificationType, enabled: bool
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO notification_settings (account_id, type, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(account_id, type) DO UPDATE SET enabled = excluded.enabled
            """,
            (account_id, notification_type.value, enabled),
        )

    def list_settings(self, account_id: int) -> list[NotificationSetting]:
        rows = self._connection.execute(
            "SELECT * FROM notification_settings WHERE account_id = ?", (account_id,)
        ).fetchall()
        return [
            NotificationSetting(
                account_id=row["account_id"],
                type=NotificationType(row["type"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

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
