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
import subprocess
import atexit
import threading
import uvicorn

# Import frontend components
from frontend.components import (
    load_css, show_message, auth_status_component,
    sync_config_component, sync_button_component, sync_results_component,
    anime_list_component
)
from frontend.auth import authenticate_user, get_auth_status, require_auth

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
if "mal_access_token" not in st.session_state:
    st.session_state.mal_access_token = None
if "mal_refresh_token" not in st.session_state:
    st.session_state.mal_refresh_token = None
if "anilist_access_token" not in st.session_state:
    st.session_state.anilist_access_token = None
if "anilist_refresh_token" not in st.session_state:
    st.session_state.anilist_refresh_token = None
if "mal_username" not in st.session_state:
    st.session_state.mal_username = None
if "anilist_username" not in st.session_state:
    st.session_state.anilist_username = None
if 'sync_history' not in st.session_state:
    st.session_state.sync_history = []
if 'last_sync_result' not in st.session_state:
    st.session_state.last_sync_result = None
if "server_started" not in st.session_state:
    st.session_state.server_started = False
if "authenticated" not in st.session_state:
    st.session_state.authenticated = {"mal": False, "anilist": False}

# Start the FastAPI server
if not st.session_state.server_started:
    def run_server():
        uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=False)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    st.session_state.server_started = True

# Initialize API clients with tokens
mal_client = MALClient(st.session_state.mal_access_token) if st.session_state.mal_access_token else None
anilist_client = AniListClient(st.session_state.anilist_access_token) if st.session_state.anilist_access_token else None

# Initialize sync manager
if mal_client and anilist_client:
    sync_manager = AnimeSyncManager(mal_client, anilist_client)
else:
    sync_manager = None

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

# Initialize API clients and sync manager
@st.cache_resource
def get_sync_manager():
    mal_client = MALClient(st.session_state.mal_access_token) if st.session_state.mal_access_token else None
    anilist_client = AniListClient(st.session_state.anilist_access_token) if st.session_state.anilist_access_token else None
    if mal_client and anilist_client:
        return AnimeSyncManager(mal_client, anilist_client)
    else:
        return None

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
    st.title("🔄 Anime List Synchronizer")
    st.markdown("Sync your anime lists between MyAnimeList and AniList")
    
    # Platform authentication
    st.header("🔑 Authentication")
    col1, col2 = st.columns(2)
    
    with col1:
        with st.container(border=True):
            st.subheader("MyAnimeList")
            if not st.session_state.authenticated["mal"]:
                if st.button("Authenticate with MyAnimeList", key="auth_mal"):
                    authenticate_user("mal")
                    st.session_state.authenticated["mal"] = True
                    st.experimental_rerun()
    
    with col2:
        with st.container(border=True):
            st.subheader("AniList")
            if not st.session_state.authenticated["anilist"]:
                if st.button("Authenticate with AniList", key="auth_anilist"):
                    authenticate_user("AniList")
                    st.session_state.authenticated["anilist"] = True
                    st.experimental_rerun()
    
    # Sync options
    st.header("⚙️ Sync Options")
    with st.expander("Advanced Options"):
        col1, col2 = st.columns(2)
        with col1:
            sync_direction = st.radio(
                "Sync Direction",
                ["Bidirectional", "MAL to AniList", "AniList to MAL"],
                index=0,
                help="Choose which direction to sync your lists"
            )
        with col2:
            sync_method = st.radio(
                "Sync Method",
                ["Smart Sync (Recommended)", "Force Overwrite"],
                index=0,
                help="Smart sync only updates missing entries, while force overwrite updates all"
            )
    
    # Sync button
    if st.button("🔄 Start Sync", type="primary", use_container_width=True, key="sync_button"):
        if not st.session_state.authenticated["mal"] or not st.session_state.authenticated["anilist"]:
            st.error("Please authenticate with both platforms")
            return
        
        # Determine sync direction
        direction_map = {
            "Bidirectional": SyncDirection.BIDIRECTIONAL,
            "MAL to AniList": SyncDirection.MAL_TO_ANILIST,
            "AniList to MAL": SyncDirection.ANILIST_TO_MAL
        }
        
        # Create sync config
        sync_config = SyncConfig(
            mal_username=st.session_state.mal_username,
            anilist_username=st.session_state.anilist_username,
            target_platform=("MyAnimeList" if "to MAL" in sync_direction else "AniList")
        )
        
        # Show progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Update progress
            progress_bar.progress(10)
            status_text.info("🔍 Fetching your anime lists...")
            
            # Perform sync
            progress_bar.progress(30)
            status_text.info("🔄 Syncing your lists...")
            
            result = sync_manager.sync_lists(
                config=sync_config,
                direction=direction_map[sync_direction]
            )
            
            # Save result
            st.session_state.last_sync_result = result
            st.session_state.sync_history.insert(0, {
                "timestamp": datetime.now().isoformat(),
                "result": result,
                "config": sync_config.dict()
            })
            
            # Show success
            progress_bar.progress(100)
            status_text.success("✅ Sync completed successfully!")
            
            # Display results
            display_sync_result(result)
            
        except Exception as e:
            progress_bar.progress(0)
            status_text.error(f"❌ Error during sync: {str(e)}")
            st.exception(e)
    
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
