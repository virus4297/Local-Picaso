import os
import time
import logging
import traceback
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from sqlmodel import Session, select
from app.main import engine, Photo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scanner")

def is_file_stable(path: str, checks: int = 3, wait: float = 0.5) -> bool:
    try:
        prev = -1
        for _ in range(checks):
            if not os.path.exists(path):
                return False
            size = os.path.getsize(path)
            if size == prev:
                return True
            prev = size
            time.sleep(wait)
        return False
    except Exception:
        logger.exception("stability check failed")
        return False

class PhotoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            self.process_new_photo(event.src_path)

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            logger.info(f"File moved into folder: {event.dest_path}")
            self.process_new_photo(event.dest_path)
            
    def process_new_photo(self, file_path):
        try:
            if not is_file_stable(file_path):
                logger.debug(f"File not stable yet: {file_path}")
                return

            with Session(engine) as session:
                statement = select(Photo).where(Photo.file_path == file_path)
                exists = session.exec(statement).first()
                if not exists:
                    new_photo = Photo(
                        file_path=file_path,
                        filename=os.path.basename(file_path),
                        status="pending"
                    )
                    session.add(new_photo)
                    session.commit()
                    logger.info(f"Indexed new photo: {new_photo.filename}")
        except Exception:
            logger.exception("Failed to process photo")

def scan_directory(path_to_watch):
    try:
        for root, _, files in os.walk(path_to_watch):
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                    PhotoHandler().process_new_photo(os.path.join(root, f))
    except Exception:
        logger.exception("Error during directory scan")

def start_scanner(path_to_watch):
    event_handler = PhotoHandler()
    observer = PollingObserver(timeout=1)
    observer.schedule(event_handler, path_to_watch, recursive=True)
    observer.start()
    logger.info(f"Watcher started on: {path_to_watch}")

    if not os.path.exists(path_to_watch):
        os.makedirs(path_to_watch, exist_ok=True)

    # Initial full scan
    scan_directory(path_to_watch)

    try:
        while True:
            scan_directory(path_to_watch)  # periodic catch-all
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
    except Exception:
        logger.exception("Scanner loop crashed")
        observer.stop()
    observer.join()