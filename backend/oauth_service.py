"""OAuth 2.0 with PKCE authentication service for MyAnimeList and AniList."""
import os
import base64
import hashlib
import secrets
from typing import Dict, Tuple

import requests
from fastapi import HTTPException

# Load environment variables
MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID")
MAL_CLIENT_SECRET = os.getenv("MAL_CLIENT_SECRET")
MAL_REDIRECT_URI = os.getenv("MAL_REDIRECT_URI")

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID")
ANILIST_CLIENT_SECRET = os.getenv("ANILIST_CLIENT_SECRET")
ANILIST_REDIRECT_URI = os.getenv("ANILIST_REDIRECT_URI")


def generate_pkce() -> Tuple[str, str]:
    """Generate PKCE code verifier and code challenge.

    Returns:
        tuple: (code_verifier, code_challenge)
    """
    # Generate a random code verifier
    code_verifier = secrets.token_urlsafe(96)
    
    # Calculate the code challenge (SHA-256 hash of the code verifier, base64 URL-safe encoded without padding)
    m = hashlib.sha256()
    m.update(code_verifier.encode("ascii"))
    code_challenge = base64.urlsafe_b64encode(m.digest()).decode("ascii")
    code_challenge = code_challenge.replace("=", "")
    
    return code_verifier, code_challenge


def get_authorization_url(platform: str) -> Tuple[str, str]:
    """Get the authorization URL for the given platform.

    Args:
        platform: Either "mal" or "anilist"

    Returns:
        tuple: (authorization_url, code_verifier)
    """
    code_verifier, code_challenge = generate_pkce()
    
    if platform == "mal":
        base_url = "https://myanimelist.net/v1/oauth2/authorize"
        params = {
            "response_type": "code",
            "client_id": MAL_CLIENT_ID,
            "code_challenge": code_challenge,
            "state": secrets.token_urlsafe(16),
            "redirect_uri": MAL_REDIRECT_URI,
        }
    elif platform == "anilist":
        base_url = "https://anilist.co/api/v2/oauth/authorize"
        params = {
            "client_id": ANILIST_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": ANILIST_REDIRECT_URI,
            "code_challenge": code_challenge,
            "state": secrets.token_urlsafe(16),
        }
    else:
        raise ValueError("Invalid platform")
    
    # Build the authorization URL
    from urllib.parse import urlencode
    auth_url = f"{base_url}?{urlencode(params)}"
    
    return auth_url, code_verifier


def exchange_code_for_token(platform: str, code: str, code_verifier: str) -> Dict[str, str]:
    """Exchange authorization code for access token.

    Args:
        platform: Either "mal" or "anilist"
        code: Authorization code
        code_verifier: PKCE code verifier

    Returns:
        dict: Token response (access_token, refresh_token, etc.)
    """
    if platform == "mal":
        token_url = "https://myanimelist.net/v1/oauth2/token"
        data = {
            "client_id": MAL_CLIENT_ID,
            "client_secret": MAL_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": MAL_REDIRECT_URI,
            "code_verifier": code_verifier,
        }
    elif platform == "anilist":
        token_url = "https://anilist.co/api/v2/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": ANILIST_CLIENT_ID,
            "client_secret": ANILIST_CLIENT_SECRET,
            "redirect_uri": ANILIST_REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier,
        }
    else:
        raise ValueError("Invalid platform")
    
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    
    return response.json()
