FROM python:3.10-slim

# Install system dependencies for AI libraries later
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 libgles2 libegl1 libglib2.0-0 libsm6 libxrender1 libxext6 libx11-6 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code
COPY . .

# Start the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]