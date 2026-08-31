from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class ProgressRecord:
    started_at: float
    updated_at: float
    percent: float
    phase: str
    ceiling: float
    expected_phase_seconds: float
    status: str = "processing"


class ProgressRegistry:
    """In-memory, body-free progress tracking for active verification requests."""

    def __init__(self, *, clock=time.monotonic, retention_seconds: float = 3600):
        self._clock = clock
        self._retention_seconds = retention_seconds
        self._records: dict[str, ProgressRecord] = {}
        self._lock = threading.Lock()

    def _cleanup(self, now: float) -> None:
        expired = [
            request_id
            for request_id, record in self._records.items()
            if now - record.updated_at > self._retention_seconds
        ]
        for request_id in expired:
            self._records.pop(request_id, None)

    def start(self, request_id: str) -> None:
        now = self._clock()
        with self._lock:
            self._cleanup(now)
            self._records[request_id] = ProgressRecord(
                started_at=now,
                updated_at=now,
                percent=1.0,
                phase="upload_validation",
                ceiling=5.0,
                expected_phase_seconds=3.0,
            )

    def update(
        self,
        request_id: str,
        percent: float,
        phase: str,
        ceiling: float,
        expected_phase_seconds: float,
    ) -> None:
        now = self._clock()
        with self._lock:
            record = self._records.get(request_id)
            if not record or record.status != "processing":
                return
            record.percent = max(record.percent, min(float(percent), 99.0))
            record.ceiling = max(
                record.percent,
                min(float(ceiling), 99.0),
            )
            record.expected_phase_seconds = max(float(expected_phase_seconds), 1.0)
            record.phase = phase
            record.updated_at = now

    def complete(self, request_id: str) -> None:
        now = self._clock()
        with self._lock:
            record = self._records.get(request_id)
            if not record:
                return
            record.percent = 100.0
            record.ceiling = 100.0
            record.phase = "completed"
            record.status = "completed"
            record.updated_at = now

    def fail(self, request_id: str) -> None:
        now = self._clock()
        with self._lock:
            record = self._records.get(request_id)
            if not record:
                return
            record.phase = "failed"
            record.status = "failed"
            record.updated_at = now

    def snapshot(self, request_id: str) -> dict | None:
        now = self._clock()
        with self._lock:
            self._cleanup(now)
            record = self._records.get(request_id)
            if not record:
                return None
            if record.status == "completed":
                displayed_percent = 100.0
                remaining = 0
            else:
                phase_elapsed = max(0.0, now - record.updated_at)
                phase_fraction = min(
                    phase_elapsed / record.expected_phase_seconds,
                    0.90,
                )
                displayed_percent = record.percent + (
                    (record.ceiling - record.percent) * phase_fraction
                )
                phase_remaining = max(
                    0.0,
                    record.expected_phase_seconds - phase_elapsed,
                )
                tail_remaining = max(0.0, 99.0 - record.ceiling) * 2.0
                remaining = round(phase_remaining + tail_remaining)
            return {
                "status": record.status,
                "phase": record.phase,
                "percent": round(displayed_percent, 1),
                "elapsed_seconds": round(max(0.0, now - record.started_at)),
                "estimated_remaining_seconds": remaining,
            }
