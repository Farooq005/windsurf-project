"""API endpoints for the Anime List Sync application."""
from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional
import os
import json
from datetime import datetime

from .auth import (
    get_mal_auth_url,
    handle_mal_callback,
    get_anilist_auth_url,
    handle_anilist_callback
)
from .anime_sync import AnimeSyncManager, SyncDirection
from .models import SyncConfig, SyncResult, AnimeEntry
from .api_clients import MALClient, AniListClient

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

@app.post("/api/sync", response_model=SyncResult)
async def sync_lists_endpoint(config: SyncConfig, direction: SyncDirection, request: Request):
    """Endpoint to trigger the anime list synchronization."""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_data = user_sessions[session_id]
    mal_token = session_data.get("mal", {}).get("access_token")
    anilist_token = session_data.get("anilist", {}).get("access_token")

    if not mal_token or not anilist_token:
        raise HTTPException(status_code=401, detail="Missing required authentication for sync")

    try:
        mal_client = MALClient()
        anilist_client = AniListClient()
        sync_manager = AnimeSyncManager(mal_client, anilist_client)

        result = await sync_manager.sync_lists(
            config=config,
            direction=direction,
            mal_token=mal_token,
            anilist_token=anilist_token
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@app.get("/api/export")
async def export_lists(request: Request):
    """Export user's anime lists to a JSON file."""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_data = user_sessions[session_id]
    mal_token = session_data.get("mal", {}).get("access_token")
    anilist_token = session_data.get("anilist", {}).get("access_token")

    if not mal_token or not anilist_token:
        raise HTTPException(status_code=401, detail="Missing required authentication")

    try:
        mal_client = MALClient()
        anilist_client = AniListClient()

        mal_list = await mal_client.get_anime_list(session_data["mal"]["username"], mal_token)
        anilist_list = await anilist_client.get_anime_list(session_data["anilist"]["username"], anilist_token)

        export_data = {
            "myanimelist": [entry.dict() for entry in mal_list],
            "anilist": [entry.dict() for entry in anilist_list],
            "exported_at": datetime.now().isoformat()
        }

        return JSONResponse(
            content=export_data,
            headers={"Content-Disposition": f"attachment; filename=anisync_export_{datetime.now().strftime('%Y%m%d')}.json"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@app.post("/api/import")
async def import_lists(request: Request, file: UploadFile = File(...)):
    """Import user's anime lists from a JSON file."""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_data = user_sessions[session_id]
    mal_token = session_data.get("mal", {}).get("access_token")
    anilist_token = session_data.get("anilist", {}).get("access_token")

    if not mal_token or not anilist_token:
        raise HTTPException(status_code=401, detail="Missing required authentication for import")

    try:
        contents = await file.read()
        import_data = json.loads(contents)

        mal_client = MALClient()
        anilist_client = AniListClient()

        mal_entries = import_data.get("myanimelist", [])
        anilist_entries = import_data.get("anilist", [])
        
        errors = []
        success_count = 0

        # Import to MAL
        for entry_data in mal_entries:
            try:
                entry = AnimeEntry(**entry_data)
                await mal_client.save_list_entry(session_data["mal"]["username"], entry, mal_token)
                success_count += 1
            except Exception as e:
                errors.append(f"Failed to import '{entry_data.get('title')}' to MAL: {e}")

        # Import to AniList
        for entry_data in anilist_entries:
            try:
                entry = AnimeEntry(**entry_data)
                await anilist_client.save_list_entry(session_data["anilist"]["username"], entry, anilist_token)
                success_count += 1
            except Exception as e:
                errors.append(f"Failed to import '{entry_data.get('title')}' to AniList: {e}")

        return {
            "success": True,
            "message": f"Import completed with {success_count} successes and {len(errors)} errors.",
            "errors": errors
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

# Mount static files for the frontend
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
