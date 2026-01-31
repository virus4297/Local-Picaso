import os
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from sqlmodel import Session
from app.main import engine, Face

# This dynamically finds the 'models' folder relative to this file
# face_engine.py is in app/services/, so we go up two levels to reach app/
current_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(current_dir, "..", "models", "face_detector.task")

def extract_faces(photo_id: int, file_path: str):
    # Debugging: This will print the EXACT path Python is looking at
    if not os.path.exists(MODEL_PATH):
        print(f"MODEL NOT FOUND AT: {os.path.abspath(MODEL_PATH)}")
        return

    try:
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.FaceDetectorOptions(base_options=base_options)
        
        with vision.FaceDetector.create_from_options(options) as detector:
            image = mp.Image.create_from_file(file_path)
            detection_result = detector.detect(image)

            if detection_result.detections:
                with Session(engine) as session:
                    for detection in detection_result.detections:
                        bbox = detection.bounding_box
                        new_face = Face(
                            photo_id=photo_id,
                            box_x=int(bbox.origin_x), 
                            box_y=int(bbox.origin_y), 
                            box_w=int(bbox.width), 
                            box_h=int(bbox.height),
                            encoding="[]" 
                        )
                        session.add(new_face)
                    session.commit()
                    print(f"🎭 Found {len(detection_result.detections)} faces in Photo ID {photo_id}")
    except Exception as e:
        print(f"Face detection failed for photo {photo_id}: {e}")