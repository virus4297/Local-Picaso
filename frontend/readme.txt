
## 🚀 Project Overview (Local Picaso / LocalVision)

This repo is a small **image ingestion + face detection** system with:

- **Backend (FastAPI)** that watches a folder, processes new photos, generates thumbnails, detects faces, and serves an API.
- **Frontend (static HTML)** that polls the backend to display thumbnails + detected faces.
- **Data storage** on disk + SQLite DB (no external cloud required).

---

## 📁 Key Folders & Files

### backend – API + Processing Engine
- Dockerfile → builds a container with Python deps + system libs needed for OpenCV / MediaPipe.
- requirements.txt → FastAPI + MediaPipe + SQLModel + OpenCV + Pillow + Watchdog.

#### main.py
- Defines `FastAPI` app, DB models (Photo, Face, Person), and endpoints:
  - `/` → status
  - `/photos` → all photo records
  - `/gallery` → processed photos with thumbnail URLs
  - `/people` → detected faces with URLs to cropped face images
  - `/faces` → raw face DB records

- Starts a background **scanner thread** on startup watching ` /app/data/photos`.

#### scanner.py
- Watches the photo folder using `watchdog` (polling observer).
- On new images:
  - Adds DB record with `status="pending"`
- On delete: removes DB record + thumbnails + face crops.
- Periodic scan loop ensures:
  - missing thumbnails are reprocessed
  - deleted files are cleaned up
  - stalled/errored items get retried

#### processor.py
- Runs periodically (from scanner loop).
- Processes `Photo` records with `status == "pending"`:
  - Creates a thumbnail (`/app/data/thumbnails/thumb_{id}_{filename}.jpg`)
  - Calls `extract_faces(...)`
  - Marks `status = "processed"` (or `error` on failure)

#### face_engine.py
- Uses **MediaPipe** face detection + **OpenCV** to:
  - detect faces in the original image
  - add a `Face` record per detection (bounding box + placeholder encoding)
  - crop the face region with padding and save to `/app/data/faces/face_{face_id}.jpg`

---

## 🧩 Frontend (index.html)
A simple static dashboard that:

- Polls `http://localhost:8000/people` to show detected face crops in a grid
- Polls `http://localhost:8000/gallery` to show thumbnails for processed photos
- Refreshes every **5 seconds** to reflect newly processed images

---

## 🗂️ Data Layout (runtime)
When running via Docker, you’ll see these folders/outputs:

- `/app/data/photos` → drop `.jpg/.jpeg/.png` here (input images)
- `/app/data/thumbnails` → generated thumbnails (`thumb_{photo.id}_{file}`)
- `/app/data/faces` → face crops (`face_{face.id}.jpg`)
- `/app/data/localvision.db` → SQLite DB with `Photo`, `Face`, `Person`

---

## ▶️ How to Run (Quick Start)

1. Make Sure Docker App is running.

From repo root:

2. ```powershell
docker-compose up --build
```

Then:

- Drop images into photos (on host)  
- Open the UI: index.html in a browser (or serve it via a simple web server)

> The backend exposes `http://localhost:8000/`, `http://localhost:8000/gallery`, `.../people`, etc.

---

## 🔍 Where to Look First (if you want to modify behavior)

### Want a new API feature?
Edit main.py (endpoints)

### Want different face detection (or add face recognition)?
Edit face_engine.py

### Want more robust processing / GPU / batching?
Edit processor.py & scanner.py

### Want UI improvements?
Edit index.html (simple DOM + fetch logic)

---

If you want, tell me what you’d like to change/extend (e.g., “add person naming and search”, “support video”, 
“show a fullscreen face viewer”, “make it run without Docker”) and I can walk you through the exact files/logic that need updates.
