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
from urllib.parse import urlparse, parse_qs

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

# Store PKCE code_verifiers by OAuth state to support frontend-based callbacks
STATE_STORE: Dict[str, Dict[str, str]] = {}

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
        # Extract state from the URL and store code_verifier mapped to state
        parsed = urlparse(auth_url)
        qs = parse_qs(parsed.query)
        state = (qs.get("state") or [None])[0]
        if not state:
            raise HTTPException(status_code=500, detail="Authorization URL missing state")
        STATE_STORE[state] = {"platform": platform, "code_verifier": code_verifier}
        return RedirectResponse(url=auth_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/auth/{platform}/callback")
async def auth_callback(platform: str, code: str, state: str, request: Request):
    """Handle OAuth callback and exchange code for tokens."""
    # Retrieve the stored code_verifier using state
    entry = STATE_STORE.get(state)
    if not entry or entry.get("platform") != platform:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    code_verifier = entry.get("code_verifier")
    
    try:
        token_data = exchange_code_for_token(platform, code, code_verifier)
        # Clean up state entry
        STATE_STORE.pop(state, None)
        # Redirect to frontend with success
        frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:8501").rstrip("/")
        return RedirectResponse(url=f"{frontend_base}/?auth_success={platform}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class TokenRequest(BaseModel):
    platform: str
    code: str
    state: str

@app.post("/auth/token")
async def exchange_token(body: TokenRequest):
    """Exchange authorization code for tokens using stored PKCE verifier via state.

    This endpoint supports public frontend redirect URIs that receive the code and state,
    then POST them here for token exchange.
    """
    platform = body.platform.lower()
    entry = STATE_STORE.get(body.state)
    if not entry or entry.get("platform") != platform:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    code_verifier = entry.get("code_verifier")
    try:
        token_data = exchange_code_for_token(platform, body.code, code_verifier)
        STATE_STORE.pop(body.state, None)
        return {"success": True, "platform": platform, "token": token_data}
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
