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
from backend.models import SyncConfig, SyncDifference


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Initialize session state
get_session_state()



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

def display_sync_result(result: Dict[str, Any]) -> None:
    """Display sync results in a user-friendly way."""
    if result.get("success_count", 0) > 0:
        st.markdown(f"""
        <div class="success-box">
            <h4>✅ Sync Completed Successfully</h4>
            <p>Successfully synced {result.get("success_count")} items.</p>
        </div>
        """, unsafe_allow_html=True)
    
    if result.get("error_count", 0) > 0:
        with st.expander(f"❌ {result.get('error_count')} Errors (Click to view)"):
            for error in result.get("errors", []):
                st.error(error)
    
    # Show differences
    if result.get("differences"):
        with st.expander("📊 Sync Details"):
            differences = result.get("differences", {})
            mal_only = differences.get("mal_only", [])
            anilist_only = differences.get("anilist_only", [])
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Only in MAL", len(mal_only))
                if mal_only:
                    st.dataframe(pd.DataFrame([{
                        "Title": item.get('title'),
                        "Status": item.get('status'),
                        "Progress": f"{item.get('episodes_watched', 0)}/{item.get('total_episodes', '?')}",
                        "Score": item.get('score', '-')
                    } for item in mal_only]), use_container_width=True)
            
            with col2:
                st.metric("Only in AniList", len(anilist_only))
                if anilist_only:
                    st.dataframe(pd.DataFrame([{
                        "Title": item.get('title'),
                        "Status": item.get('status'),
                        "Progress": f"{item.get('episodes_watched', 0)}/{item.get('total_episodes', '?')}",
                        "Score": item.get('score', '-')
                    } for item in anilist_only]), use_container_width=True)

def get_platform_icon(platform: str) -> str:
    """Get platform icon."""
    icons = {
        "MyAnimeList": "📚",
        "AniList": "📱"
    }
    return icons.get(platform, "")

def main():
    st.sidebar.title("AniSync")
    
    # Navigation
    with st.sidebar:
        selected = option_menu(
            menu_title=None,
            options=["Sync Anime", "Settings", "About"],
            icons=["arrow-repeat", "gear", "info-circle"],
            default_index=0,
        )
    
    if selected == "Sync Anime":
        render_sync_page()
    elif selected == "Settings":
        render_settings()
    else:  # About
        render_about()

def render_sync_page():
    st.title(" AniSync")

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
                logout('mal')

    # AniList Authentication Column
    with col2:
        auth_status_component("AniList", anilist_authed, st.session_state.get("anilist_username"))
        if not anilist_authed:
            if st.button("Login with AniList", key="anilist_login"):
                init_anilist_auth()
        else:
            if st.button("Logout from AniList", key="anilist_logout"):
                logout('anilist')

    # Handle auth callback centrally after rendering buttons
    handle_auth_callback()

    # If both are authenticated, show sync options
    if mal_authed and anilist_authed:
        st.markdown("---")
        st.header(" Sync Options")

        direction_map = {
            "Bidirectional": "bidirectional",
            "MAL to AniList": "mal_to_anilist",
            "AniList to MAL": "anilist_to_mal"
        }

        sync_direction_label = st.radio(
            "Sync Direction",
            list(direction_map.keys()),
            index=0,
            help="Choose which direction to sync your lists"
        )

        if st.button(" Start Sync", type="primary", use_container_width=True, key="sync_button"):
            with st.spinner("Synchronizing lists..."):
                try:
                    payload = {
                        "config": {
                            "mal_username": st.session_state.get("mal_username"),
                            "anilist_username": st.session_state.get("anilist_username"),
                            "target_platform": "MyAnimeList"
                        },
                        "direction": direction_map[sync_direction_label]
                    }
                    response = requests.post(
                        f"{API_BASE_URL}/api/sync",
                        json=payload,
                        cookies=st.session_state.get('cookies', {}),
                        timeout=300 # 5 minutes timeout for sync
                    )
                    response.raise_for_status()
                    result = response.json()
                    st.session_state.last_sync_result = result
                    st.rerun()
                except requests.exceptions.HTTPError as e:
                    try:
                        error_detail = e.response.json().get("detail", e.response.text)
                    except json.JSONDecodeError:
                        error_detail = e.response.text
                    st.error(f"Sync failed: {error_detail}")
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    logger.exception("Sync failed")

    else:
        st.info("Please log in to both MyAnimeList and AniList to enable syncing.")
    
    # Show last sync result if available
    if st.session_state.last_sync_result:
        st.header("📊 Last Sync Result")
        display_sync_result(st.session_state.last_sync_result)

def render_sync_history():
    st.title("📜 Sync History")
    st.info("Sync history is not available in this version.")

def render_settings():
    st.title("⚙️ Settings")
    

    
    st.header("Application Settings")
    auto_sync = st.checkbox("Enable auto-sync", value=True,
                          help="Automatically sync when changes are detected")
    
    

    st.header("Data Management")

    # Export functionality
    if st.button("Export Lists to JSON"):
        try:
            response = requests.get(f"{API_BASE_URL}/api/export", cookies=st.session_state.get('cookies', {}))
            response.raise_for_status()
            st.session_state['export_data'] = response.json()
            st.success("Export data generated! Click the download button below.")
        except Exception as e:
            st.error(f"Failed to export data: {e}")

    if 'export_data' in st.session_state and st.session_state['export_data']:
        st.download_button(
            label="Download JSON Export",
            data=json.dumps(st.session_state['export_data'], indent=2),
            file_name=f"anisync_export_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            on_click=lambda: st.session_state.pop('export_data', None)  # Clear after download
        )

    # Import functionality
    uploaded_file = st.file_uploader("Import Lists from JSON", type="json")
    if uploaded_file is not None:
        if st.button("Process Import File"):
            with st.spinner("Importing lists..."):
                try:
                    files = {'file': (uploaded_file.name, uploaded_file, 'application/json')}
                    response = requests.post(f"{API_BASE_URL}/api/import", files=files, cookies=st.session_state.get('cookies', {}))
                    response.raise_for_status()
                    result = response.json()
                    st.success(result.get("message", "Import completed!"))
                    if result.get("errors"):
                        with st.expander("View import errors"):
                            for error in result["errors"]:
                                st.error(error)
                except Exception as e:
                    st.error(f"Failed to import data: {e}")

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
    1. Go to the 'Sync Anime' page.
    2. Click the authentication buttons for MyAnimeList and AniList.
    3. Follow the on-screen prompts to log in and authorize the application.
    4. Once authenticated, choose your sync options and click 'Start Sync'.
    
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
