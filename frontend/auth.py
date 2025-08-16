"""
Authentication components for the Streamlit UI.
"""
import streamlit as st
import requests
from typing import Optional, Dict, Any
import json
import os

# API base URL
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

__all__ = ["authenticate_user", "get_auth_status", "require_auth"]

def get_session_state() -> Dict[str, Any]:
    """Get or initialize the session state."""
    if not hasattr(st, 'session_state'):
        st.session_state.update({
            'authenticated': False,
            'mal_authenticated': False,
            'anilist_authenticated': False,
            'mal_username': None,
            'anilist_username': None,
            'access_tokens': {}
        })
    return st.session_state

def check_auth() -> bool:
    """Check if the user is authenticated with either MAL or AniList."""
    state = get_session_state()
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
            return state['authenticated']
    except Exception as e:
        st.error(f"Error checking authentication status: {e}")
    return False

def authenticate_user(platform: str):
    """Redirect to backend auth endpoint."""
    import requests
    from streamlit import session_state as st_session
    
    # Reset any existing tokens
    st_session.pop(f"{platform}_access_token", None)
    
    # Trigger backend auth redirect
    response = requests.get(f"http://localhost:8000/auth/{platform}")
    if response.status_code != 200:
        st.error(f"Failed to start authentication: {response.text}")
        return
    
    # Redirect to the authorization URL
    st_session.auth_redirect_url = response.url
    st.experimental_rerun()

def get_auth_status(platform: str) -> bool:
    """Check if user is authenticated for the given platform."""
    from streamlit import session_state as st_session
    return f"{platform}_access_token" in st_session

def handle_auth_callback() -> None:
    """Handle OAuth2 callback from the URL parameters."""
    query_params = st.experimental_get_query_params()
    
    # Handle MAL callback
    if 'code' in query_params and 'state' in query_params:
        try:
            response = requests.get(
                f"{API_BASE_URL}/auth/mal/callback",
                params={"code": query_params['code'][0], "state": query_params['state'][0]}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    st.success("Successfully authenticated with MyAnimeList!")
                    st.experimental_set_query_params()  # Clear the URL parameters
                    st.experimental_rerun()
                else:
                    st.error(f"Failed to authenticate with MyAnimeList: {data.get('error')}")
            else:
                st.error(f"Failed to authenticate with MyAnimeList: {response.text}")
        except Exception as e:
            st.error(f"Error handling MAL callback: {e}")
    
    # Handle AniList callback
    # This part is tricky because both callbacks use 'code' and 'state'.
    # We need a way to distinguish them. We assume if the 'state' is not in our MAL records,
    # it must be for AniList. This relies on the backend storing state separately.
    elif 'code' in query_params and 'state' in query_params and 'mal_auth_url' not in st.session_state:
        try:
            response = requests.get(
                f"{API_BASE_URL}/auth/anilist/callback",
                params={"code": query_params['code'][0], "state": query_params['state'][0]}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    st.success("Successfully authenticated with AniList!")
                    st.experimental_set_query_params()  # Clear the URL parameters
                    st.experimental_rerun()
                else:
                    st.error(f"Failed to authenticate with AniList: {data.get('error')}")
            else:
                st.error(f"Failed to authenticate with AniList: {response.text}")
        except Exception as e:
            st.error(f"Error handling AniList callback: {e}")


def logout() -> None:
    """Log out the current user."""
    try:
        response = requests.post(f"{API_BASE_URL}/auth/logout", cookies=st.session_state.get('cookies', {}))
        if response.status_code == 200:
            st.session_state.update({
                'authenticated': False,
                'mal_authenticated': False,
                'anilist_authenticated': False,
                'mal_username': None,
                'anilist_username': None,
                'access_tokens': {}
            })
            st.experimental_rerun()
        else:
            st.error(f"Failed to log out: {response.text}")
    except Exception as e:
        st.error(f"Error logging out: {e}")

def require_auth(platform: str = 'any') -> bool:
    """
    Require authentication for a specific platform.
    
    Args:
        platform: 'mal', 'anilist', or 'any'
        
    Returns:
        bool: True if authenticated, False otherwise
    """
    state = get_session_state()
    
    if platform == 'mal' and not state['mal_authenticated']:
        st.warning("Please authenticate with MyAnimeList to continue.")
        authenticate_user('mal')
        return False
    elif platform == 'anilist' and not state['anilist_authenticated']:
        st.warning("Please authenticate with AniList to continue.")
        authenticate_user('anilist')
        return False
    elif platform == 'any' and not (state['mal_authenticated'] or state['anilist_authenticated']):
        st.warning("Please authenticate with at least one platform to continue.")
        return False
        
    return True
