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

def init_mal_auth() -> None:
    """Initialize MAL OAuth2 flow."""
    try:
        response = requests.get(f"{API_BASE_URL}/auth/mal/init")
        if response.status_code == 200:
            auth_url = response.json().get('url')
            if auth_url:
                st.session_state['mal_auth_url'] = auth_url
                st.markdown(f"[Click here to authenticate with MyAnimeList]({auth_url})")
                st.experimental_rerun()
            else:
                st.error("Failed to get authentication URL")
        else:
            st.error(f"Failed to initialize MAL authentication: {response.text}")
    except Exception as e:
        st.error(f"Error initializing MAL authentication: {e}")

def init_anilist_auth() -> None:
    """Initialize AniList OAuth2 flow."""
    try:
        response = requests.get(f"{API_BASE_URL}/auth/anilist/init")
        if response.status_code == 200:
            auth_url = response.json().get('url')
            if auth_url:
                st.session_state['anilist_auth_url'] = auth_url
                st.markdown(f"[Click here to authenticate with AniList]({auth_url})")
                st.experimental_rerun()
            else:
                st.error("Failed to get authentication URL")
        else:
            st.error(f"Failed to initialize AniList authentication: {response.text}")
    except Exception as e:
        st.error(f"Error initializing AniList authentication: {e}")

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

def get_auth_status() -> Dict[str, Any]:
    """Get the current authentication status."""
    state = get_session_state()
    return {
        'authenticated': state['authenticated'],
        'mal_authenticated': state['mal_authenticated'],
        'anilist_authenticated': state['anilist_authenticated'],
        'mal_username': state['mal_username'],
        'anilist_username': state['anilist_username']
    }

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
        init_mal_auth()
        return False
    elif platform == 'anilist' and not state['anilist_authenticated']:
        st.warning("Please authenticate with AniList to continue.")
        init_anilist_auth()
        return False
    elif platform == 'any' and not (state['mal_authenticated'] or state['anilist_authenticated']):
        st.warning("Please authenticate with at least one platform to continue.")
        return False
        
    return True
