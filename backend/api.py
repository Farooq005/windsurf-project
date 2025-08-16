"""API endpoints for the Anime List Sync application."""
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional
import os
import logging
from starlette.middleware.sessions import SessionMiddleware

from .oauth_service import get_authorization_url, exchange_code_for_token

app = FastAPI(
    title="Anime List Sync API",
    description="API for syncing anime lists between MyAnimeList and AniList",
    version="1.0.0"
)

# CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware for request.session support
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret"),
)

# Store tokens in memory (in production, use a secure session store or database)
user_sessions: Dict[str, Dict] = {}

class AuthResponse(BaseModel):
    success: bool
    url: str
    error: Optional[str] = None

class CallbackResponse(BaseModel):
    success: bool
    token: Optional[Dict] = None
    username: Optional[str] = None
    error: Optional[str] = None

router = APIRouter()

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}

@router.get("/auth/{platform}")
async def auth_redirect(platform: str, request: Request):
    """Redirect to the platform's authorization URL."""
    try:
        auth_url, code_verifier = get_authorization_url(platform)
        # Store code_verifier in session
        request.session[f"{platform}_code_verifier"] = code_verifier
        return RedirectResponse(url=auth_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/auth/{platform}/callback")
async def auth_callback(platform: str, code: str, state: str, request: Request):
    """Handle OAuth callback and exchange code for tokens."""
    # Retrieve the stored code_verifier
    code_verifier = request.session.get(f"{platform}_code_verifier")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Code verifier not found")
    
    try:
        token_data = exchange_code_for_token(platform, code, code_verifier)
        # Store tokens securely (e.g., in database or session)
        request.session[f"{platform}_access_token"] = token_data["access_token"]
        request.session[f"{platform}_refresh_token"] = token_data.get("refresh_token")
        # Redirect to frontend with success
        frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:8501").rstrip("/")
        return RedirectResponse(url=f"{frontend_base}/?auth_success={platform}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

app.include_router(router)

@app.get("/auth/session")
async def get_session(request: Request) -> Dict:
    """Get the current session data."""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        return {"authenticated": False}
    
    session_data = user_sessions.get(session_id, {})
    return {
        "authenticated": bool(session_data),
        "mal_authenticated": "mal" in session_data,
        "anilist_authenticated": "anilist" in session_data,
        "mal_username": session_data.get("mal", {}).get("username") if "mal" in session_data else None,
        "anilist_username": session_data.get("anilist", {}).get("username") if "anilist" in session_data else None
    }

@app.post("/auth/logout")
async def logout(request: Request):
    """Log out the current user."""
    session_id = request.cookies.get("session_id")
    if session_id in user_sessions:
        del user_sessions[session_id]
    
    response = JSONResponse(content={"success": True})
    response.delete_cookie("session_id")
    return response

# Mount static files for the frontend (optional during dev/CI)
if os.path.isdir("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
else:
    logging.getLogger(__name__).warning("Static directory 'frontend/dist' not found; skipping mount.")
