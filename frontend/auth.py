"""
Authentication components for the Streamlit UI.
"""
import streamlit as st
import requests
from typing import Optional, Dict, Any, Tuple
import json
import os
import base64
import hashlib

# API/Frontend configuration
API_BASE_URL = os.getenv("API_BASE_URL", "")  # not used for OAuth anymore
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://list-sync-anime.streamlit.app").rstrip("/")

# Provider endpoints
MAL_AUTH_URL = "https://myanimelist.net/v1/oauth2/authorize"
MAL_TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
ANILIST_AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
ANILIST_TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

__all__ = ["authenticate_user", "get_auth_status", "require_auth", "handle_auth_callback"]

def get_session_state() -> Dict[str, Any]:
    """Get or initialize the session state."""
    ss = st.session_state
    # Ensure keys exist with correct types
    if 'authenticated' not in ss or not isinstance(ss.get('authenticated'), dict):
        ss['authenticated'] = {'mal': False, 'anilist': False}
    if 'mal_username' not in ss:
        ss['mal_username'] = None
    if 'anilist_username' not in ss:
        ss['anilist_username'] = None
    if 'access_tokens' not in ss:
        ss['access_tokens'] = {}
    if 'oauth_state_store' not in ss or not isinstance(ss.get('oauth_state_store'), dict):
        ss['oauth_state_store'] = {}
    return ss

def check_auth() -> bool:
    """Check if the user is authenticated with either MAL or AniList."""
    state = get_session_state()
    # If no backend, infer from session tokens/flags
    if not API_BASE_URL:
        auth = st.session_state.get('authenticated', {})
        return bool(auth.get('mal') or auth.get('anilist') or st.session_state.get('mal_access_token') or st.session_state.get('anilist_access_token'))
    try:
        response = requests.get(f"{API_BASE_URL}/auth/session", cookies=st.session_state.get('cookies', {}))
        if response.status_code == 200:
            data = response.json()
            state.update({
                'authenticated': data.get('authenticated', False),
                'mal_authenticated': data.get('mal_authenticated', False),
                'anilist_authenticated': data.get('anilist_authenticated', False),
                'mal_username': data.get('mal_username'),
                'anilist_username': data.get('anilist_username')
            })
            return bool(state['authenticated'])
    except Exception:
        pass
    return bool(st.session_state.get('mal_access_token') or st.session_state.get('anilist_access_token'))

def _generate_pkce() -> Tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(64)).decode("ascii").rstrip("=")
    m = hashlib.sha256()
    m.update(verifier.encode("ascii"))
    challenge = base64.urlsafe_b64encode(m.digest()).decode("ascii").rstrip("=")
    return verifier, challenge

def authenticate_user(platform: str):
    """Prepare provider authorization URL using PKCE and present it to the user."""
    from streamlit import session_state as st_session

    platform = platform.lower()
    if platform not in ("mal", "anilist"):
        st.error("Unsupported platform")
        return

    client_id = os.getenv("MAL_CLIENT_ID") if platform == "mal" else os.getenv("ANILIST_CLIENT_ID")
    if not client_id:
        st.error(f"Missing {'MAL' if platform=='mal' else 'AniList'} client ID in environment")
        return

    verifier, challenge = _generate_pkce()
    state = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")
    redirect_uri = f"{FRONTEND_BASE_URL}/?provider={platform}"

    # Store mapping from state to verifier
    ss = get_session_state()
    ss['oauth_state_store'][state] = {"platform": platform, "code_verifier": verifier}

    if platform == "mal":
        params = {
            "response_type": "code",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "redirect_uri": redirect_uri,
        }
        base_url = MAL_AUTH_URL
    else:
        params = {
            "response_type": "code",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "redirect_uri": redirect_uri,
        }
        base_url = ANILIST_AUTH_URL

    from urllib.parse import urlencode
    auth_url = f"{base_url}?{urlencode(params)}"
    st_session.auth_redirect_url = auth_url
    st_session.auth_platform = platform
    st.rerun()

def get_auth_status(platform: str) -> bool:
    """Check if user is authenticated for the given platform."""
    from streamlit import session_state as st_session
    return f"{platform}_access_token" in st_session

def handle_auth_callback() -> None:
    """Handle OAuth2 callback from public redirect to the Streamlit app.

    Expected URL params: code, state, provider in {mal, anilist}
    """
    q = st.query_params
    # st.query_params returns a mapping of str -> str | list[str]
    def _first(val):
        if isinstance(val, list):
            return val[0] if val else None
        return val
    code = _first(q.get('code'))
    state = _first(q.get('state'))
    provider = _first(q.get('provider'))

    if not (code and state and provider):
        return

    platform = provider.lower()
    if platform not in ("mal", "anilist"):
        st.error("Unknown provider in callback.")
        return

    # Retrieve verifier from session
    ss = get_session_state()
    entry = ss['oauth_state_store'].get(state)
    if not entry or entry.get('platform') != platform:
        st.error("Invalid or expired state. Please restart authentication.")
        return
    verifier = entry['code_verifier']

    # Build token request
    redirect_uri = f"{FRONTEND_BASE_URL}/?provider={platform}"
    try:
        if platform == "mal":
            client_id = os.getenv("MAL_CLIENT_ID")
            client_secret = os.getenv("MAL_CLIENT_SECRET")
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            }
            resp = requests.post(MAL_TOKEN_URL, data=data, timeout=15)
        else:
            client_id = os.getenv("ANILIST_CLIENT_ID")
            client_secret = os.getenv("ANILIST_CLIENT_SECRET")
            data = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": verifier,
            }
            resp = requests.post(ANILIST_TOKEN_URL, data=data, timeout=15)

        if resp.status_code != 200:
            st.error(f"Failed to exchange code: {resp.status_code} {resp.text}")
            return
        token = resp.json()
        access = token.get("access_token")
        refresh = token.get("refresh_token")
        if platform == "mal":
            st.session_state.mal_access_token = access
            st.session_state.mal_refresh_token = refresh
            st.session_state.authenticated = st.session_state.get("authenticated", {"mal": False, "anilist": False})
            st.session_state.authenticated["mal"] = True
        else:
            st.session_state.anilist_access_token = access
            st.session_state.anilist_refresh_token = refresh
            st.session_state.authenticated = st.session_state.get("authenticated", {"mal": False, "anilist": False})
            st.session_state.authenticated["anilist"] = True
        # Cleanup used state
        ss['oauth_state_store'].pop(state, None)
        st.success(f"Successfully authenticated with {'MyAnimeList' if platform=='mal' else 'AniList'}!")
        # Clear query params and rerun
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    except Exception as e:
        st.error(f"Error finalizing authentication: {e}")


def logout() -> None:
    """Log out the current user."""
    # Local session-only logout
    st.session_state.update({
        'mal_access_token': None,
        'mal_refresh_token': None,
        'anilist_access_token': None,
        'anilist_refresh_token': None,
        'mal_username': None,
        'anilist_username': None,
    })
    # Auth flags
    st.session_state.authenticated = {'mal': False, 'anilist': False}
    st.session_state.pop('auth_redirect_url', None)
    st.session_state.pop('auth_platform', None)
    # Clear any pending oauth state mapping
    ss = get_session_state()
    ss['oauth_state_store'].clear()
    st.rerun()

def require_auth(platform: str = 'any') -> bool:
    """
    Require authentication for a specific platform.
    
    Args:
        platform: 'mal', 'anilist', or 'any'
        
    Returns:
        bool: True if authenticated, False otherwise
    """
    ss = get_session_state()
    auth_flags = ss.get('authenticated', {'mal': False, 'anilist': False})
    mal_ok = bool(auth_flags.get('mal') or st.session_state.get('mal_access_token'))
    anilist_ok = bool(auth_flags.get('anilist') or st.session_state.get('anilist_access_token'))

    if platform == 'mal':
        if not mal_ok:
            st.warning("Please authenticate with MyAnimeList to continue.")
            return False
        return True
    elif platform == 'anilist':
        if not anilist_ok:
            st.warning("Please authenticate with AniList to continue.")
            return False
        return True
    else:  # any
        if not (mal_ok or anilist_ok):
            st.warning("Please authenticate with at least one platform to continue.")
            return False
        return True
