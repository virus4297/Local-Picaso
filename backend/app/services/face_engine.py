import json
import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from deepface import DeepFace
from sqlmodel import Session, select
from app.main import engine, Face, Person

# Path to your model
MODEL_PATH = '/app/app/models/face_detector.task'
FACES_DIR = '/app/data/faces'
os.makedirs(FACES_DIR, exist_ok=True)

EMBEDDING_SIZE = 128
DISTANCE_THRESHOLD = 0.45
RECOGNITION_MODEL = None


def get_recognition_model():
    global RECOGNITION_MODEL
    if RECOGNITION_MODEL is None:
        RECOGNITION_MODEL = DeepFace.build_model('Facenet')
    return RECOGNITION_MODEL


def normalize_embedding(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def image_to_embedding(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return np.zeros(EMBEDDING_SIZE, dtype=np.float32)

    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    model = get_recognition_model()

    try:
        representation = DeepFace.represent(
            img_path=None,
            img_array=rgb_image,
            model_name='Facenet',
            model=model,
            enforce_detection=False,
            detector_backend='opencv'
        )

        if isinstance(representation, list) and representation:
            embedding = np.asarray(representation[0].get('embedding', []), dtype=np.float32)
        elif isinstance(representation, dict) and 'embedding' in representation:
            embedding = np.asarray(representation['embedding'], dtype=np.float32)
        else:
            embedding = np.zeros(EMBEDDING_SIZE, dtype=np.float32)
    except Exception:
        embedding = np.zeros(EMBEDDING_SIZE, dtype=np.float32)

    if embedding.size == 0:
        embedding = np.zeros(EMBEDDING_SIZE, dtype=np.float32)

    return normalize_embedding(embedding)


def person_centroid(session: Session, person_id: int) -> np.ndarray | None:
    embeddings = []
    faces = session.exec(select(Face).where(Face.person_id == person_id)).all()
    for face in faces:
        try:
            face_embedding = np.asarray(json.loads(face.encoding), dtype=np.float32)
        except Exception:
            continue
        if face_embedding.size:
            embeddings.append(normalize_embedding(face_embedding))

    if not embeddings:
        return None
    centroid = np.mean(embeddings, axis=0)
    return normalize_embedding(centroid)


def find_best_person(session: Session, face_embedding: np.ndarray) -> int:
    face_embedding = normalize_embedding(face_embedding)
    best_person = None
    best_distance = 1.0

    persons = session.exec(select(Person)).all()
    for person in persons:
        centroid = person_centroid(session, person.id)
        if centroid is None:
            continue

        distance = 1.0 - float(np.dot(centroid, face_embedding))
        if distance < best_distance:
            best_distance = distance
            best_person = person

    if best_person and best_distance < DISTANCE_THRESHOLD:
        return best_person.id

    new_person = Person(name='Unknown')
    session.add(new_person)
    session.commit()
    return new_person.id


def extract_faces(photo_id: int, file_path: str):
    """Detects faces, generates embeddings, groups by person, and saves crops."""
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.FaceDetectorOptions(base_options=base_options)

    with vision.FaceDetector.create_from_options(options) as detector:
        mp_image = mp.Image.create_from_file(file_path)
        cv2_img = cv2.imread(file_path)
        detection_result = detector.detect(mp_image)

        if detection_result.detections:
            with Session(engine) as session:
                for detection in detection_result.detections:
                    bbox = detection.bounding_box

                    new_face = Face(
                        photo_id=photo_id,
                        box_x=int(bbox.origin_x), box_y=int(bbox.origin_y),
                        box_w=int(bbox.width), box_h=int(bbox.height),
                        encoding='[]'
                    )
                    session.add(new_face)
                    session.commit()

                    x, y, w, h = new_face.box_x, new_face.box_y, new_face.box_w, new_face.box_h
                    pad_w, pad_h = int(w * 0.2), int(h * 0.2)
                    y1, y2 = max(0, y - pad_h), min(cv2_img.shape[0], y + h + pad_h)
                    x1, x2 = max(0, x - pad_w), min(cv2_img.shape[1], x + w + pad_w)

                    face_crop = cv2_img[y1:y2, x1:x2]
                    face_filename = f'face_{new_face.id}.jpg'
                    save_path = os.path.join(FACES_DIR, face_filename)
                    cv2.imwrite(save_path, face_crop)

                    face_embedding = image_to_embedding(face_crop)
                    person_id = find_best_person(session, face_embedding)

                    new_face.encoding = json.dumps(face_embedding.tolist())
                    new_face.person_id = person_id
                    session.add(new_face)
                    session.commit()

                    print(f'Snipped and saved face: {face_filename} assigned to person {person_id}')
