import os
import threading
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Field, SQLModel, create_engine, Session, select
from sqlalchemy import event

# 1. Database Configuration (Using Absolute Path for Docker Stability)
DATABASE_URL = "sqlite:////app/data/localvision.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# 2. Database Models
class Person(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "Unknown"

class Face(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    photo_id: int = Field(foreign_key="photo.id")
    person_id: Optional[int] = Field(default=None, foreign_key="person.id")
    box_x: int
    box_y: int
    box_w: int
    box_h: int
    encoding: str = "[]"

class Photo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_path: str = Field(unique=True)
    filename: str
    status: str = "pending" # pending, processing, processed, error

# 3. Lifespan (Startup/Shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("LocalVision Engine is initializing...")
    # Ensure directories exist BEFORE creating DB or starting scanner
    os.makedirs("/app/data/photos", exist_ok=True)
    os.makedirs("/app/data/thumbnails", exist_ok=True)
    os.makedirs("/app/data/faces", exist_ok=True)
    
    SQLModel.metadata.create_all(engine)

    from app.services.scanner import start_scanner
    watch_path = "/app/data/photos"
    
    print(f"Starting scanner watching: {watch_path}")
    scanner_thread = threading.Thread(target=start_scanner, args=(watch_path,), daemon=True)
    scanner_thread.start()

    yield
    print("LocalVision Engine is shutting down...")

# 4. App Definition
app = FastAPI(title="LocalVision API", lifespan=lifespan)

# Static File Mounting (Done once, safely)
app.mount("/content/photos", StaticFiles(directory="/app/data/photos"), name="photos")
app.mount("/content/thumbs", StaticFiles(directory="/app/data/thumbnails"), name="thumbnails")
app.mount("/content/faces", StaticFiles(directory="/app/data/faces"), name="faces")
app.mount("/ui", StaticFiles(directory="/app/frontend"), name="frontend")

# 5. API Models
class PersonNameUpdate(BaseModel):
    name: str

# 6. Endpoints
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "LocalVision is running!",
        "ui": "/ui/index.html"
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # This allows your index.html to "talk" to the Pi
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/photos")
def get_photos():
    with Session(engine) as session:
        return session.exec(select(Photo)).all()

@app.get("/people")
def get_people_gallery():
    try:
        with Session(engine) as session:
            people = []
            persons = session.exec(select(Person)).all()

            for person in persons:
                face = session.exec(select(Face).where(Face.person_id == person.id).limit(1)).first()
                if not face:
                    continue
                people.append({
                    "person_id": person.id,
                    "name": person.name,
                    "face_id": face.id,
                    "photo_id": face.photo_id,
                    "url": f"content/faces/face_{face.id}.jpg"
                })

            unassigned_faces = session.exec(select(Face).where(Face.person_id == None)).all()
            for face in unassigned_faces:
                people.append({
                    "person_id": None,
                    "name": "Unknown",
                    "face_id": face.id,
                    "photo_id": face.photo_id,
                    "url": f"content/faces/face_{face.id}.jpg"
                })

            return people
    except Exception as e:
        print(f"Error in /people endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/people/{person_id}")
def update_person_name(person_id: int, update: PersonNameUpdate):
    try:
        with Session(engine) as session:
            person = session.get(Person, person_id)
            if not person:
                raise HTTPException(status_code=404, detail="Person not found")

            person.name = update.name.strip() or "Unknown"
            session.add(person)
            session.commit()
            return {"person_id": person.id, "name": person.name}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating person name: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/gallery")
def get_gallery():
    with Session(engine) as session:
        statement = select(Photo).where(Photo.status == "processed")
        photos = session.exec(statement).all()
        return [
            {
                "id": p.id,
                "filename": p.filename,
                "full_url": f"/content/photos/{p.filename}",
                "thumb_url": f"/content/thumbs/thumb_{p.id}_{p.filename}"
            }
            for p in photos
        ]

@app.get("/faces")
def get_faces():
    with Session(engine) as session:
        return session.exec(select(Face)).all()