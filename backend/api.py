"""API endpoints for the Anime List Sync application."""
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional
import os

from .auth import (
    get_mal_auth_url,
    handle_mal_callback,
    get_anilist_auth_url,
    handle_anilist_callback
)

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

@app.get("/auth/mal/init")
async def init_mal_auth(request: Request) -> AuthResponse:
    """Initialize MAL OAuth2 flow."""
    try:
        auth_url = get_mal_auth_url(request)
        return {"success": True, "url": auth_url}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/auth/mal/callback")
async def mal_callback(request: Request) -> CallbackResponse:
    """Handle MAL OAuth2 callback."""
    try:
        token_data, username = await handle_mal_callback(request)
        # Store token in session
        session_id = request.cookies.get("session_id")
        if not session_id or session_id not in user_sessions:
            session_id = os.urandom(16).hex()
            user_sessions[session_id] = {}
        
        user_sessions[session_id]["mal"] = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "username": username
        }
        
        response = {
            "success": True,
            "token": token_data,
            "username": username
        }
        
        # Create response with session cookie
        response = JSONResponse(content=response)
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=30 * 24 * 3600  # 30 days
        )
        
        return response
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/auth/anilist/init")
async def init_anilist_auth(request: Request) -> AuthResponse:
    """Initialize AniList OAuth2 flow."""
    try:
        auth_url = get_anilist_auth_url(request)
        return {"success": True, "url": auth_url}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/auth/anilist/callback")
async def anilist_callback(request: Request) -> CallbackResponse:
    """Handle AniList OAuth2 callback."""
    try:
        token_data, username = await handle_anilist_callback(request)
        # Store token in session
        session_id = request.cookies.get("session_id")
        if not session_id or session_id not in user_sessions:
            session_id = os.urandom(16).hex()
            user_sessions[session_id] = {}
        
        user_sessions[session_id]["anilist"] = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "username": username
        }
        
        response = {
            "success": True,
            "token": token_data,
            "username": username
        }
        
        # Create response with session cookie
        response = JSONResponse(content=response)
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=30 * 24 * 3600  # 30 days
        )
        
        return response
        
    except Exception as e:
        return {"success": False, "error": str(e)}

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

# Mount static files for the frontend
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
