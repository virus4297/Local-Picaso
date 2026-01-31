import os
import threading
from contextlib import asynccontextmanager
from typing import Optional

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
class Photo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_path: str = Field(unique=True)
    filename: str
    status: str = "pending"

# 3. The Lifespan (The most important part)
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 LocalVision Engine is initializing...")
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
    print("🛑 LocalVision Engine is shutting down...")

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