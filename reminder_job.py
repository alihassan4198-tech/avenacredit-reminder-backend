"""AWS Lambda entry point for sending due reminders, triggered by an EventBridge schedule.

Replaces the always-running worker.py loop: each invocation processes one batch, the same as one worker tick.
"""
import uuid

from app.db import SessionLocal
from app.services.scheduler import process_due_reminders


def handler(event=None, context=None) -> dict[str, int]:
    request_id = getattr(context, "aws_request_id", None) or uuid.uuid4().hex
    worker_id = f"lambda-{request_id[:12]}"

    db = SessionLocal()
    try:
        result = process_due_reminders(db, batch_size=200, worker_id=worker_id)
        print(f"reminder_job: {result}", flush=True)
        return result
    finally:
        db.close()


if __name__ == "__main__":
    handler()
