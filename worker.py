import time
import uuid

from app.config import settings
from app.db import SessionLocal, engine
from app.models import Base
from app.services.scheduler import process_due_reminders


def main() -> None:
    Base.metadata.create_all(bind=engine)
    worker_id = f"worker-{uuid.uuid4().hex[:12]}"

    while True:
        db = SessionLocal()
        try:
            result = process_due_reminders(db, batch_size=200, worker_id=worker_id)
            print(f"worker: {result}", flush=True)
        finally:
            db.close()

        time.sleep(max(1, settings.worker_poll_seconds))


if __name__ == "__main__":
    main()
