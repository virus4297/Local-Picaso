import os
import logging
from PIL import Image
from sqlmodel import Session, select
from app.main import engine, Photo
from app.services.face_engine import extract_faces

THUMB_PATH = "/app/data/thumbnails"
SIZE = (300, 300)

def process_photos():
    """Finds pending photos and creates thumbnails with immediate status locking."""
    logger = logging.getLogger("processor")
    
    with Session(engine) as session:
        # 1. Only grab photos that are truly 'pending'
        statement = select(Photo).where(Photo.status == "pending")
        pending_photos = session.exec(statement).all()

        if not pending_photos:
            return

        logger.info(f"Starting processing for {len(pending_photos)} new items...")
        os.makedirs(THUMB_PATH, exist_ok=True)

        for photo in pending_photos:
            # --- THE LOCK: Change status to 'processing' immediately ---
            photo.status = "processing"
            session.add(photo)
            session.commit() 

            try:
                # Open the original
                with Image.open(photo.file_path) as img:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    img.thumbnail(SIZE)
                    
                    # Save it
                    thumb_name = f"thumb_{photo.id}_{photo.filename}"
                    save_path = os.path.join(THUMB_PATH, thumb_name)
                    img.save(save_path, "JPEG")
                    
                    logger.info(f"Thumbnail: {photo.filename}")
                    
                    # Extract faces                    
                    extract_faces(photo.id, photo.file_path)

                    # Mark as processed
                    photo.status = "processed"
                    session.add(photo)
                    session.commit() # Save progress for this specific photo
            
            except Exception as e:
                logger.error(f"Error processing {photo.filename}: {e}")
                photo.status = "error"
                session.add(photo)
                session.commit()