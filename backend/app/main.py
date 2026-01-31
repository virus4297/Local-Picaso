import os
import threading
from contextlib import asynccontextmanager
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from sqlmodel import Field, SQLModel, create_engine, Session
from sqlalchemy import event

# 1. Database Configuration
DATABASE_URL = "sqlite:///./data/localvision.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# 2. Database Model
# --- MODELS ---
class Person(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "Unknown"

class Face(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    photo_id: int = Field(foreign_key="photo.id")
    person_id: Optional[int] = Field(default=None, foreign_key="person.id")
    
    # Coordinates for the specific face crop
    box_x: int
    box_y: int
    box_w: int
    box_h: int
    
    # The mathematical fingerprint
    encoding: str 

class Photo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_path: str = Field(unique=True)
    filename: str
    status: str = "pending" # pending, processed, error

# 3. The Lifespan (The most important part)
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("LocalVision Engine is initializing...")
    SQLModel.metadata.create_all(engine)

    from app.services.scanner import start_scanner
    watch_path = os.environ.get("WATCH_PATH")
    if not watch_path:
        if os.path.exists("/app/data/photos"):
            watch_path = "/app/data/photos"
        else:
            watch_path = os.path.abspath(os.path.join(os.getcwd(), "data", "photos"))

    os.makedirs(watch_path, exist_ok=True)
    print(f"Starting scanner watching: {watch_path}")

    scanner_thread = threading.Thread(target=start_scanner, args=(watch_path,), daemon=True)
    scanner_thread.start()

    yield
    print("LocalVision Engine is shutting down...")

# 4. Define the App ONLY ONCE
app = FastAPI(title="LocalVision API", lifespan=lifespan)

@app.get("/")
def root():
    return {"status": "online", "message": "Everything is working!"}

@app.get("/photos")
def get_photos():
    with Session(engine) as session:
        from sqlmodel import select
        return session.exec(select(Photo)).all()
    
os.makedirs("/app/data/photos", exist_ok=True)
os.makedirs("/app/data/thumbnails", exist_ok=True)
os.makedirs("/app/data/faces", exist_ok=True) # This is the one causing the crash!

# 3. Now you can safely mount them
app.mount("/content/photos", StaticFiles(directory="/app/data/photos"), name="photos")
app.mount("/content/thumbs", StaticFiles(directory="/app/data/thumbnails"), name="thumbnails")
app.mount("/content/faces", StaticFiles(directory="/app/data/faces"), name="faces")

# 5. Static Files Serving
# This lets you go to http://localhost:8000/content/thumbnails/your_image.jpg
app.mount("/content/photos", StaticFiles(directory="/app/data/photos"), name="photos")
app.mount("/content/thumbs", StaticFiles(directory="/app/data/thumbnails"), name="thumbnails")
app.mount("/content/faces", StaticFiles(directory="/app/data/faces"), name="faces")

@app.get("/people")
def get_people_gallery():
    """Returns a list of all detected face crops."""
    with Session(engine) as session:
        faces = session.exec(select(Face)).all()
        return [
            {
                "face_id": f.id,
                "photo_id": f.photo_id,
                "url": f"/content/faces/face_{f.id}.jpg"
            }
            for f in faces
        ]
    
@app.get("/gallery")
def get_gallery():
    with Session(engine) as session:
        from sqlmodel import select
        # Only show photos that are successfully processed
        statement = select(Photo).where(Photo.status == "processed")
        photos = session.exec(statement).all()
        
        # We transform the data to include the URL for the frontend
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
        from sqlmodel import select
        # This queries the Face table we created
        faces = session.exec(select(Face)).all()
        return faces