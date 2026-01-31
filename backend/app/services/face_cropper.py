import os
import cv2
from sqlmodel import Session, select
from app.main import engine, Face, Photo

FACES_DIR = "/app/data/faces"

def generate_face_crops():
    """Generates small JPG files for every detected face."""
    os.makedirs(FACES_DIR, exist_ok=True)
    
    with Session(engine) as session:
        faces = session.exec(select(Face)).all()
        
        for face in faces:
            save_path = os.path.join(FACES_DIR, f"face_{face.id}.jpg")
            if os.path.exists(save_path):
                continue
                
            photo = session.get(Photo, face.photo_id)
            if not photo: continue
            
            img = cv2.imread(photo.file_path)
            if img is None: continue
            
            # Crop using the coordinates from the DB
            x, y, w, h = face.box_x, face.box_y, face.box_w, face.box_h
            pad_w, pad_h = int(w * 0.2), int(h * 0.2)
            
            y1, y2 = max(0, y - pad_h), min(img.shape[0], y + h + pad_h)
            x1, x2 = max(0, x - pad_w), min(img.shape[1], x + w + pad_w)
            
            face_img = img[y1:y2, x1:x2]
            cv2.imwrite(save_path, face_img)
            print(f"✂️ Cropped face {face.id} from {photo.filename}")