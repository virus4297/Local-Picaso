import os
import time
import logging
from threading import Lock
from sqlmodel import Session, select
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from app.main import engine, Photo, Face
from app.services.processor import process_photos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scanner")

class PhotoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            self.process_new_photo(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.remove_deleted_photo(event.src_path)

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            self.process_new_photo(event.dest_path)

    def process_new_photo(self, file_path):
        """Indexes a new file into the database."""
        try:
            with Session(engine) as session:
                statement = select(Photo).where(Photo.file_path == file_path)
                exists = session.exec(statement).first()
                if exists:
                    return

                logger.info(f"📸 Indexing: {os.path.basename(file_path)}")
                new_photo = Photo(
                    file_path=file_path,
                    filename=os.path.basename(file_path),
                    status="pending"
                )
                session.add(new_photo)
                session.commit()
        except Exception:
            logger.exception(f"❌ Failed to index {file_path}")

    def remove_deleted_photo(self, file_path):
        """Cleans up DB, Thumbnails, and Face crops for a deleted file."""
        with Session(engine) as session:
            statement = select(Photo).where(Photo.file_path == file_path)
            photo = session.exec(statement).first()
            
            if photo:
                # 1. Delete Thumbnail
                thumb_path = f"/app/data/thumbnails/thumb_{photo.id}_{photo.filename}"
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                    logger.info(f"🗑️ Deleted thumbnail for {photo.filename}")

                # 2. Delete Face Crops
                faces = session.exec(select(Face).where(Face.photo_id == photo.id)).all()
                for face in faces:
                    face_crop_path = f"/app/data/faces/face_{face.id}.jpg"
                    if os.path.exists(face_crop_path):
                        os.remove(face_crop_path)
                    session.delete(face)

                # 3. Delete Photo Record
                session.delete(photo)
                session.commit()
                logger.info(f"🚮 Full cleanup complete for {photo.filename}")

# Configuration & Locks
pending_sizes: dict[str, int] = {}
pending_lock = Lock()
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL", "10"))

def scan_directory(path_to_watch):
    """Periodic health check: cleans ghosts, fixes missing thumbs, and finds new files."""
    try:
        with Session(engine) as session:
            # 1. Self-Healing: Reset 'error' to 'pending'
            failed_photos = session.exec(select(Photo).where(Photo.status == "error")).all()
            for photo in failed_photos:
                photo.status = "pending"
                session.add(photo)

            # 2. Health Check: If thumb is missing, re-process
            processed_photos = session.exec(select(Photo).where(Photo.status == "processed")).all()
            for photo in processed_photos:
                thumb_path = f"/app/data/thumbnails/thumb_{photo.id}_{photo.filename}"
                if not os.path.exists(thumb_path):
                    logger.warning(f"♻️ Thumb missing for {photo.filename}. Re-processing...")
                    photo.status = "pending"
                    session.add(photo)

            # 3. Ghost Cleanup: If file is gone from disk, remove from DB
            all_db_photos = session.exec(select(Photo)).all()
            existing_in_db = set()
            for photo in all_db_photos:
                if not os.path.exists(photo.file_path):
                    logger.warning(f"👻 Ghost found: {photo.filename}. Cleaning up...")
                    PhotoHandler().remove_deleted_photo(photo.file_path)
                else:
                    existing_in_db.add(photo.file_path)
            
            session.commit()

            # 4. Walk the directory to find new files
            for root, _, files in os.walk(path_to_watch):
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                        full_path = os.path.join(root, f)
                        if full_path not in existing_in_db:
                            PhotoHandler().process_new_photo(full_path)

        # 5. Kick the processor to handle 'pending' items
        process_photos()

    except Exception:
        logger.exception("Error during directory scan")

def start_scanner(path_to_watch):
    """Initializes the real-time observer and the periodic scanner loop."""
    os.makedirs(path_to_watch, exist_ok=True)
    
    event_handler = PhotoHandler()
    observer = PollingObserver(timeout=1)
    observer.schedule(event_handler, path_to_watch, recursive=True)
    observer.start()
    
    logger.info(f"🚀 Scanner and Observer active on: {path_to_watch}")

    try:
        while True:
            scan_directory(path_to_watch)
            time.sleep(SCAN_INTERVAL)
    except Exception:
        logger.exception("Scanner loop crashed")
        observer.stop()
    observer.join()