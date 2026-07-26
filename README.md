# Backend

FastAPI + MongoDB backend for ClassReminder.

## Setup

1. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in the values:
   ```bash
   cp .env.example .env
   ```
   - `MONGO_URI` / `DATABASE_NAME`: your MongoDB connection.
   - `JWT_SECRET_KEY`: a long random string.
   - `GEMINI_API_KEY`: required for AI features (Google Gemini).

4. Run the server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Requirements

- A running MongoDB instance.
- A valid `GEMINI_API_KEY` (needed for Gemini-powered features).
