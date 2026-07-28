from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.db.session import engine


class SchedulerLeaseStore:
    def __init__(self, lease_seconds: int) -> None:
        self._lease_seconds = lease_seconds

    def claim(self, job_id: int) -> str | None:
        now = datetime.now(UTC)
        owner = str(uuid.uuid4())
        expires_at = now + timedelta(seconds=self._lease_seconds)
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE scheduled_jobs
                    SET lease_owner = :owner,
                        lease_expires_at = :expires_at,
                        run_status = 'queued',
                        last_run_at = :now,
                        updated_at = :now,
                        last_error = ''
                    WHERE id = :job_id
                      AND (lease_expires_at IS NULL OR lease_expires_at < :now)
                    """
                ),
                {
                    "owner": owner,
                    "expires_at": expires_at,
                    "now": now,
                    "job_id": job_id,
                },
            )
        return owner if result.rowcount == 1 else None

    def mark_running(self, job_id: int, owner: str) -> bool:
        return self._update_owned(job_id, owner, run_status="running") == 1

    def finish(self, job_id: int, owner: str, *, status: str, error: str = "") -> bool:
        now = datetime.now(UTC)
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE scheduled_jobs
                    SET lease_owner = '',
                        lease_expires_at = NULL,
                        run_status = :status,
                        last_finished_at = :now,
                        last_error = :error,
                        updated_at = :now
                    WHERE id = :job_id AND lease_owner = :owner
                    """
                ),
                {
                    "status": status,
                    "error": error[:2000],
                    "now": now,
                    "job_id": job_id,
                    "owner": owner,
                },
            )
        return result.rowcount == 1

    def _update_owned(self, job_id: int, owner: str, **values: object) -> int:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    f"UPDATE scheduled_jobs SET {assignments} "
                    "WHERE id = :job_id AND lease_owner = :owner"
                ),
                {**values, "job_id": job_id, "owner": owner},
            )
        return result.rowcount
