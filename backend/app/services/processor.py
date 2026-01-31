import os
import logging
from PIL import Image
from sqlmodel import Session, select
from app.main import engine, Photo

THUMB_PATH = "/app/data/thumbnails"
SIZE = (300, 300)


def process_photos():
    """Finds pending photos and creates thumbnails."""
    logger = logging.getLogger("processor")
    logger.info("Starting photo processing...")
    with Session(engine) as session:
        statement = select(Photo).where(Photo.status == "pending")
        pending_photos = session.exec(statement).all()

        if not pending_photos:
            return

        os.makedirs(THUMB_PATH, exist_ok=True)

        for photo in pending_photos:
            try:
                # Open the original
                with Image.open(photo.file_path) as img:
                    # Convert to RGB if it's a PNG with transparency (prevents errors)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    img.thumbnail(SIZE)
                    
                    # Save it
                    thumb_name = f"thumb_{photo.id}_{photo.filename}"
                    save_path = os.path.join(THUMB_PATH, thumb_name)
                    img.save(save_path, "JPEG")
                    
                    # Mark as processed
                    photo.status = "processed"
                    session.add(photo)
            
            except Exception as e:
                print(f"Error processing {photo.filename}: {e}")
                photo.status = "error"
                session.add(photo)
        
        session.commit()