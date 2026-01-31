import os
import time
import logging
import traceback
from app.services.processor import process_photos
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from sqlmodel import Session, select
from app.main import engine, Photo
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scanner")
logger.setLevel(logging.DEBUG)  # <-- more verbose for debugging

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
        logger.debug(f"Event created: {event.src_path} (is_dir={event.is_directory})")
        if not event.is_directory and event.src_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            logger.debug("on_created -> process_new_photo")
            self.process_new_photo(event.src_path)

    def on_moved(self, event):
        logger.debug(f"Event moved: src={getattr(event,'src_path',None)} dest={getattr(event,'dest_path',None)}")
        if not event.is_directory and event.dest_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            logger.info(f"File moved into folder: {event.dest_path}")
            self.process_new_photo(event.dest_path)

    def process_new_photo(self, file_path):
        logger.debug(f"process_new_photo called for: {file_path}")
        try:
            if not is_file_stable(file_path):
                logger.debug(f"File not stable yet: {file_path}")
                return
            logger.debug(f"File stable, checking DB: {file_path}")
            with Session(engine) as session:
                statement = select(Photo).where(Photo.file_path == file_path)
                exists = session.exec(statement).first()
                if exists:
                    logger.debug("Already indexed, skipping")
                    return
                # Index - log before/after
                logger.info(f"Indexing: {file_path}")
                new_photo = Photo(
                    file_path=file_path,
                    filename=os.path.basename(file_path),
                    status="pending"
                )
                session.add(new_photo)
                session.commit()
                logger.info(f"Indexed new photo: {new_photo.filename}")
        except Exception:
            logger.exception("Failed to process new photo")

    def on_deleted(self, event):
        if not event.is_directory:
            logger.info(f"🗑️ File deleted from folder: {event.src_path}")
            self.remove_deleted_photo(event.src_path)

def remove_deleted_photo(self, file_path):
    with Session(engine) as session:
        statement = select(Photo).where(Photo.file_path == file_path)
        photo = session.exec(statement).first()
        
        if photo:
            # 1. Delete the Thumbnail
            thumb_path = f"/app/data/thumbnails/thumb_{photo.id}_{photo.filename}"
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
                logger.info(f"🗑️ Deleted thumbnail: {thumb_path}")

            # 2. Delete all associated Face Crops
            from app.main import Face
            faces = session.exec(select(Face).where(Face.photo_id == photo.id)).all()
            for face in faces:
                face_crop_path = f"/app/data/faces/face_{face.id}.jpg"
                if os.path.exists(face_crop_path):
                    os.remove(face_crop_path)
                session.delete(face) # Remove face record from DB too

            # 3. Delete the Photo record
            session.delete(photo)
            session.commit()
            logger.info(f"🚮 Full cleanup complete for {photo.filename}")
        with Session(engine) as session:
            statement = select(Photo).where(Photo.file_path == file_path)
            photo = session.exec(statement).first()
            
            if photo:
                # 1. (Optional) Delete the thumbnail file too
                # 2. Delete the DB record
                session.delete(photo)
                session.commit()
                logger.info(f"Removed {os.path.basename(file_path)} from database.")

pending_sizes: dict[str, int] = {}
pending_lock = Lock()
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL", "5"))

def scan_directory(path_to_watch):
    with Session(engine) as session:
        # Find everything that failed and set it back to pending
        failed_photos = session.exec(select(Photo).where(Photo.status == "error")).all()
        for photo in failed_photos:
            photo.status = "pending"
            session.add(photo)
        session.commit()
    try:
            # Get everything currently marked as 'processed'
            db_photos = session.exec(select(Photo).where(Photo.status == "processed")).all()
            
            for photo in db_photos:
                # Path to the expected thumbnail
                thumb_path = f"/app/data/thumbnails/thumb_{photo.id}_{photo.filename}"
                
                # If the photo is processed but the thumbnail is GONE
                if not os.path.exists(thumb_path):
                    logger.warning(f"♻️ Thumbnail missing for {photo.filename}. Re-processing...")
                    photo.status = "pending" # Reset to pending so the processor picks it up
                    session.add(photo)
            
            session.commit()
            
            # Now trigger the processor to fix the 'pending' ones
            from app.services.processor import process_photos
            process_photos()
    except Exception:
        logger.exception("Error during thumbnail health check")
    try:
        with Session(engine) as session:
            # Get everything currently in the DB
            db_photos = session.exec(select(Photo)).all()
            existing = {photo.file_path for photo in db_photos}
            
            for photo in db_photos:
                # If the DB says it exists, but the folder says it doesn't...
                if not os.path.exists(photo.file_path):
                    logger.warning(f"Found ghost record: {photo.filename}. Cleaning up...")
                    session.delete(photo)
            
            session.commit()

        for root, _, files in os.walk(path_to_watch):
            for f in files:
                if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                full = os.path.join(root, f)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue

                if full in existing:
                    with pending_lock:
                        pending_sizes.pop(full, None)
                    continue

                with pending_lock:
                    prev = pending_sizes.get(full)
                    if prev is None:
                        pending_sizes[full] = size
                        continue  # first observation, wait for next scan
                    if prev != size:
                        pending_sizes[full] = size
                        continue  # size changed, wait for stabilization
                    # size stable across two scans — process it
                    pending_sizes.pop(full, None)

                PhotoHandler().process_new_photo(full)
    
    except Exception:
        logger.exception("Error during full directory scan")

def start_scanner(path_to_watch):
    # ensure directory exists before scheduling observer
    if not os.path.exists(path_to_watch):
        os.makedirs(path_to_watch, exist_ok=True)

    event_handler = PhotoHandler()
    observer = PollingObserver(timeout=1)
    observer.schedule(event_handler, path_to_watch, recursive=True)
    observer.start()
    logger.info(f"Watcher started on: {path_to_watch}")

    # Initial full scan
    scan_directory(path_to_watch)

    try:
        while True:
            scan_directory(path_to_watch)  # use SCAN_INTERVAL
            time.sleep(SCAN_INTERVAL)
    except KeyboardInterrupt:
        observer.stop()
    except Exception:
        logger.exception("Scanner loop crashed")
        observer.stop()
    observer.join()