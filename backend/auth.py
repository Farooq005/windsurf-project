"""Authentication module for MAL and AniList OAuth2 flows."""
import os
import base64
import json
import secrets
import logging
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode, parse_qs, urlparse

import requests
from fastapi import Request
from fastapi.responses import RedirectResponse

def get_required_env_var(name: str) -> str:
    """Get a required environment variable or raise an exception."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value

# Configure logging
logger = logging.getLogger(__name__)

# Load and validate environment variables
try:
    MAL_CLIENT_ID = get_required_env_var("MAL_CLIENT_ID")
    MAL_CLIENT_SECRET = get_required_env_var("MAL_CLIENT_SECRET")
    ANILIST_CLIENT_ID = get_required_env_var("ANILIST_CLIENT_ID")
    ANILIST_CLIENT_SECRET = get_required_env_var("ANILIST_CLIENT_SECRET")
    BASE_URL = os.getenv("BASE_URL", "https://list-sync-anime.streamlit.app/")
    
    # Validate BASE_URL format
    if not BASE_URL.startswith(('http://', 'https://')):
        raise ValueError("BASE_URL must start with http:// or https://")
    
    # Ensure BASE_URL doesn't end with a slash for consistency
    BASE_URL = BASE_URL.rstrip('/')
    
except ValueError as e:
    logger.error(f"Configuration error: {str(e)}")
    raise

# OAuth2 endpoints
MAL_AUTH_URL = "https://myanimelist.net/v1/oauth2/authorize"
MAL_TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
ANILIST_AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
ANILIST_TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

# Store OAuth2 states for CSRF protection
oauth_states = {}

def generate_state() -> str:
    """Generate a random state for OAuth2 CSRF protection."""
    return secrets.token_urlsafe(16)

def get_mal_auth_url(request: Request) -> str:
    """Generate the MyAnimeList OAuth2 authorization URL."""
    if not MAL_CLIENT_ID:
        raise ValueError("MAL_CLIENT_ID is not configured")
    
    state = generate_state()
    code_verifier = generate_state()
    oauth_states[state] = {"type": "mal", "code_verifier": code_verifier}

    params = {
        "client_id": MAL_CLIENT_ID,
        "response_type": "code",
        "state": state,
        "code_challenge": code_verifier,
        "code_challenge_method": "plain",
        "redirect_uri": f"{BASE_URL}/auth/mal/callback"
    }
    
    return f"{MAL_AUTH_URL}?{urlencode(params)}"

async def handle_mal_callback(request: Request) -> Tuple[Dict, str]:
    """Handle the MyAnimeList OAuth2 callback."""
    query_params = dict(request.query_params)
    code = query_params.get("code")
    state = query_params.get("state")
    
    if not code or not state:
        raise ValueError("Missing code or state in callback")
    
    if state not in oauth_states:
        raise ValueError("Invalid state parameter")
    
    # Exchange code for access token
    data = {
        "client_id": MAL_CLIENT_ID,
        "client_secret": MAL_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": oauth_states[state].get("code_verifier"),
        "redirect_uri": f"{BASE_URL}/auth/mal/callback"
    }
    
    response = requests.post(MAL_TOKEN_URL, data=data)
    response.raise_for_status()
    token_data = response.json()
    
    # Get user info
    user_info = get_mal_user_info(token_data["access_token"])
    
    # Clean up state
    del oauth_states[state]
    
    return token_data, user_info["name"]

def get_mal_user_info(access_token: str) -> Dict:
    """Get user info from MyAnimeList using access token."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get("https://api.myanimelist.net/v2/users/@me", headers=headers)
    response.raise_for_status()
    return response.json()

def get_anilist_auth_url(request: Request) -> str:
    """Generate the AniList OAuth2 authorization URL."""
    if not ANILIST_CLIENT_ID:
        raise ValueError("ANILIST_CLIENT_ID is not configured")
    
    state = generate_state()
    oauth_states[state] = {"type": "anilist"}
    
    params = {
        "client_id": ANILIST_CLIENT_ID,
        "response_type": "code",
        "state": state,
        "redirect_uri": f"{BASE_URL}/auth/anilist/callback"
    }
    
    return f"{ANILIST_AUTH_URL}?{urlencode(params)}"

async def handle_anilist_callback(request: Request) -> Tuple[Dict, str]:
    """Handle the AniList OAuth2 callback."""
    query_params = dict(request.query_params)
    code = query_params.get("code")
    state = query_params.get("state")
    
    if not code or not state:
        raise ValueError("Missing code or state in callback")
    
    if state not in oauth_states:
        raise ValueError("Invalid state parameter")
    
    # Exchange code for access token
    data = {
        "client_id": ANILIST_CLIENT_ID,
        "client_secret": ANILIST_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"{BASE_URL}/auth/anilist/callback"
    }
    
    response = requests.post(ANILIST_TOKEN_URL, json=data)
    response.raise_for_status()
    token_data = response.json()
    
    # Get user info
    user_info = get_anilist_user_info(token_data["access_token"])
    
    # Clean up state
    del oauth_states[state]
    
    return token_data, user_info["name"]

def get_anilist_user_info(access_token: str) -> Dict:
    """Get user info from AniList using access token."""
    headers = {"Authorization": f"Bearer {access_token}"}
    query = """
    query {
        Viewer {
            id
            name
            about
            avatar {
                large
            }
            bannerImage
            options {
                titleLanguage
            }
        }
    }
    """
    response = requests.post(
        "https://graphql.anilist.co",
        json={"query": query},
        headers=headers
    )
    response.raise_for_status()
    return response.json()["data"]["Viewer"]
