# Backend API

FastAPI backend for AI Paperwork Assistant.

## Run locally
```bash
cp .env.example .env
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8008
```

## Docker
```bash
docker build -t paperwork-backend .
docker run --env-file .env -p 8008:8008 paperwork-backend
```

## Main responsibilities
- authentication: register, login, forgot password, reset password
- document intake and upload completion
- OCR and document parsing
- AI analysis and field extraction
- workflow, comments, versions, admin APIs
