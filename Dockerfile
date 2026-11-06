# SITEWISE Hugging Face Docker Space (owner: Dev C)
# Stage 1: build React frontend (skipped gracefully if frontend/package.json doesn't exist yet)
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/ ./
RUN if [ -f package.json ]; then npm ci || npm install; npm run build; else mkdir -p dist; fi

# Stage 2: Python API serving the built frontend
FROM python:3.11-slim
RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH HF_HOME=/home/user/.cache/huggingface PYTHONUNBUFFERED=1
WORKDIR /home/user/app
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .
COPY --chown=user --from=web /web/dist ./frontend/dist
RUN rmdir frontend/dist 2>/dev/null || true; mkdir -p data && chown -R user data
USER user
EXPOSE 7860
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
