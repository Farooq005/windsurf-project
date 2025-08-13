import streamlit as st
from streamlit_option_menu import option_menu
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import logging
import requests
from typing import Dict, Any, Optional, List
import pandas as pd

# Import frontend components
from frontend.components import (
    load_css, show_message, auth_status_component,
    sync_config_component, sync_button_component, sync_results_component,
    anime_list_component
)
from frontend.auth import (
    get_session_state, check_auth, init_mal_auth, init_anilist_auth,
    handle_auth_callback, logout, get_auth_status, require_auth
)

# Import backend modules
from backend.models import SyncConfig, SyncResult, SyncDifference
from backend.anime_sync import AnimeSyncManager, SyncDirection
from backend.api_clients import MALClient, AniListClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Initialize session state
get_session_state()

# Initialize API clients with empty tokens (will be set during auth)
mal_client = MALClient()
anilist_client = AniListClient()

# Initialize sync manager
sync_manager = AnimeSyncManager(mal_client, anilist_client)

# Configure page
st.set_page_config(
    page_title="AniSync - Anime List Synchronizer",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .success-box {
        background-color: #e8f5e9;
        border-left: 5px solid #4caf50;
        padding: 1em;
        margin: 1em 0;
        border-radius: 0 4px 4px 0;
    }
    .error-box {
        background-color: #ffebee;
        border-left: 5px solid #f44336;
        padding: 1em;
        margin: 1em 0;
        border-radius: 0 4px 4px 0;
    }
    .info-box {
        background-color: #e3f2fd;
        border-left: 5px solid #2196f3;
        padding: 1em;
        margin: 1em 0;
        border-radius: 0 4px 4px 0;
    }
    .sync-button {
        width: 100%;
        margin: 1em 0;
    }
    .platform-card {
        padding: 1.5em;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1em;
    }
    .mal-card {
        border-left: 4px solid #2e51a2;
    }
    .anilist-card {
        border-left: 4px solid #02a9ff;
    }
    .stats-card {
        text-align: center;
        padding: 1em;
        border-radius: 8px;
        margin: 0.5em;
        background-color: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)

def display_sync_result(result: SyncResult) -> None:
    """Display sync results in a user-friendly way."""
    if result.success_count > 0:
        st.markdown(f"""
        <div class="success-box">
            <h4>✅ Sync Completed Successfully</h4>
            <p>Successfully synced {result.success_count} items.</p>
        </div>
        """, unsafe_allow_html=True)
    
    if result.error_count > 0:
        with st.expander(f"❌ {result.error_count} Errors (Click to view)"):
            for error in result.errors:
                st.error(error)
    
    # Show differences
    if result.differences:
        with st.expander("📊 Sync Details"):
            mal_only = result.differences.get("mal_only", [])
            anilist_only = result.differences.get("anilist_only", [])
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Only in MAL", len(mal_only))
                if mal_only:
                    st.dataframe(pd.DataFrame([{
                        "Title": item.title,
                        "Status": item.status,
                        "Progress": f"{item.episodes_watched or 0}/{item.total_episodes or '?'}",
                        "Score": item.score or "-"
                    } for item in mal_only]), use_container_width=True)
            
            with col2:
                st.metric("Only in AniList", len(anilist_only))
                if anilist_only:
                    st.dataframe(pd.DataFrame([{
                        "Title": item.title,
                        "Status": item.status,
                        "Progress": f"{item.episodes_watched or 0}/{item.total_episodes or '?'}",
                        "Score": item.score or "-"
                    } for item in anilist_only]), use_container_width=True)

def get_platform_icon(platform: str) -> str:
    """Get platform icon."""
    icons = {
        "MyAnimeList": "📚",
        "AniList": "📱"
    }
    return icons.get(platform, "📋")

# Initialize session state
if 'sync_history' not in st.session_state:
    st.session_state.sync_history = []
if 'last_sync_result' not in st.session_state:
    st.session_state.last_sync_result = None

# Initialize API clients and sync manager
@st.cache_resource
def get_sync_manager():
    return AnimeSyncManager(MALClient(), AniListClient())

sync_manager = get_sync_manager()

def main():
    st.sidebar.title("AniSync")
    
    # Navigation
    with st.sidebar:
        selected = option_menu(
            menu_title=None,
            options=["Sync Anime", "Sync History", "Settings", "About"],
            icons=["arrow-repeat", "clock-history", "gear", "info-circle"],
            default_index=0,
        )
    
    if selected == "Sync Anime":
        render_sync_page()
    elif selected == "Sync History":
        render_sync_history()
    elif selected == "Settings":
        render_settings()
    else:  # About
        render_about()

def render_sync_page():
    st.title("🔄 AniSync")

    # Check authentication status
    mal_authed, anilist_authed = get_auth_status()

    col1, col2 = st.columns(2)

    # MyAnimeList Authentication Column
    with col1:
        auth_status_component("MyAnimeList", mal_authed, st.session_state.get("mal_username"))
        if not mal_authed:
            if st.button("Login with MyAnimeList", key="mal_login"):
                init_mal_auth()
        else:
            if st.button("Logout from MyAnimeList", key="mal_logout"):
                logout("mal")

    # AniList Authentication Column
    with col2:
        auth_status_component("AniList", anilist_authed, st.session_state.get("anilist_username"))
        if not anilist_authed:
            if st.button("Login with AniList", key="anilist_login"):
                init_anilist_auth()
        else:
            if st.button("Logout from AniList", key="anilist_logout"):
                logout("anilist")

    # Handle auth callback centrally after rendering buttons
    handle_auth_callback()

    # If both are authenticated, show sync options
    if mal_authed and anilist_authed:
        st.markdown("---")
        st.header("⚙️ Sync Options")

        direction_map = {
            "Bidirectional": SyncDirection.BIDIRECTIONAL,
            "MAL to AniList": SyncDirection.MAL_TO_ANILIST,
            "AniList to MAL": SyncDirection.ANILIST_TO_MAL
        }

        sync_direction_label = st.radio(
            "Sync Direction",
            list(direction_map.keys()),
            index=0,
            help="Choose which direction to sync your lists"
        )

        if st.button("🔄 Start Sync", type="primary", use_container_width=True, key="sync_button"):
            sync_config = SyncConfig(
                mal_username=st.session_state.get("mal_username"),
                anilist_username=st.session_state.get("anilist_username"),
                target_platform="MyAnimeList"  # This could be made configurable
            )

            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                status_text.info("🔍 Fetching your anime lists...")
                progress_bar.progress(25)

                result = sync_manager.sync_lists(
                    config=sync_config,
                    direction=direction_map[sync_direction_label]
                )

                st.session_state.last_sync_result = result
                st.session_state.sync_history.insert(0, {
                    "timestamp": datetime.now().isoformat(),
                    "result": result,
                    "config": sync_config.dict()
                })

                progress_bar.progress(100)
                status_text.success("✅ Sync completed successfully!")
                st.rerun()

            except Exception as e:
                progress_bar.progress(0)
                status_text.error(f"❌ Error during sync: {str(e)}")
                logger.exception("Sync failed")

    else:
        st.info("Please log in to both MyAnimeList and AniList to enable syncing.")
    
    # Show last sync result if available
    if st.session_state.last_sync_result:
        st.header("📊 Last Sync Result")
        display_sync_result(st.session_state.last_sync_result)

def render_sync_history():
    st.title("📜 Sync History")
    
    if not st.session_state.sync_history:
        st.info("No sync history available. Perform a sync to see history here.")
        return
    
    for i, entry in enumerate(st.session_state.sync_history):
        with st.expander(f"Sync at {entry['timestamp']}"):
            st.json(entry)

def render_settings():
    st.title("⚙️ Settings")
    
    st.header("API Configuration")
    st.markdown("""
    ### MyAnimeList API
    - [Get MAL API Key](https://myanimelist.net/apiconfig)
    - Required scopes: `write`
    
    ### AniList API
    - [Get AniList API Key](https://anilist.co/api/v2/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=token)
    - Required scopes: `write`
    """)
    
    st.header("Application Settings")
    auto_sync = st.checkbox("Enable auto-sync", value=True,
                          help="Automatically sync when changes are detected")
    
    if st.button("Clear Sync History", type="secondary"):
        st.session_state.sync_history = []
        st.success("Sync history cleared!")

def render_about():
    st.title("ℹ️ About AniSync")
    
    st.markdown("""
    ## AniSync - Anime List Synchronizer
    
    Keep your MyAnimeList and AniList accounts in sync with ease!
    
    ### Features
    - 🔄 Bidirectional sync between MAL and AniList
    - ⚡ Smart syncing to avoid duplicates
    - 📊 Detailed sync reports
    - 🔐 Secure authentication
    
    ### How to Use
    1. Enter your MAL and AniList usernames
    2. Provide API access tokens (get them from the links in Settings)
    3. Choose sync options
    4. Click "Start Sync"
    
    ### Privacy
    - Your data never leaves your browser
    - API tokens are stored only in your session
    - No data is collected or stored on our servers
    
    ### Version
    v1.0.0
    
    [GitHub Repository](https://github.com/yourusername/anisync) | [Report an Issue](https://github.com/yourusername/anisync/issues)
    """)

if __name__ == "__main__":
    main()
