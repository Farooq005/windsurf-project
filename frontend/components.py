"""UI components for the Streamlit app."""
import streamlit as st
from typing import Dict, Any, Optional, List, Callable

# Custom CSS for the app
def load_css():
    st.markdown("""
    <style>
        .stButton>button {
            width: 100%;
            border-radius: 20px;
            border: 1px solid #4CAF50;
            background-color: #4CAF50;
            color: white;
            padding: 10px 24px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
        }
        .stButton>button:hover {
            background-color: #45a049;
            border: 1px solid #45a049;
        }
        .stTextInput>div>div>input,
        .stTextArea>div>div>textarea,
        .stSelectbox>div>div>div>div {
            border-radius: 10px;
            padding: 8px 12px;
        }
        .stProgress>div>div>div>div {
            background-color: #4CAF50;
        }
        .success-msg {
            color: #4CAF50;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .error-msg {
            color: #f44336;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .warning-msg {
            color: #ff9800;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
    </style>
    """, unsafe_allow_html=True)

def show_message(message: str, type: str = "info"):
    """Display a styled message."""
    if type == "success":
        st.markdown(f'<div class="success-msg">✅ {message}</div>', unsafe_allow_html=True)
    elif type == "error":
        st.markdown(f'<div class="error-msg">❌ {message}</div>', unsafe_allow_html=True)
    elif type == "warning":
        st.markdown(f'<div class="warning-msg">⚠️ {message}</div>', unsafe_allow_html=True)
    else:
        st.info(message)

def auth_status_component():
    """Display authentication status component."""
    status = st.session_state.get('auth_status', {})
    
    with st.sidebar:
        st.subheader("Authentication Status")
        
        # MAL Status
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("**MAL:**")
        with col2:
            if status.get('mal_authenticated'):
                st.success(f"✅ {status.get('mal_username', 'Connected')}")
            else:
                st.warning("❌ Not connected")
        
        # AniList Status
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("**AniList:**")
        with col2:
            if status.get('anilist_authenticated'):
                st.success(f"✅ {status.get('anilist_username', 'Connected')}")
            else:
                st.warning("❌ Not connected")
        
        st.markdown("---")

def sync_config_component() -> Dict[str, Any]:
    """Render sync configuration component."""
    st.subheader("Sync Configuration")
    
    # Sync direction
    direction = st.radio(
        "Sync Direction:",
        ["MAL → AniList", "AniList → MAL", "Bidirectional Sync"],
        horizontal=True,
        key="sync_direction"
    )
    
    # Sync options
    with st.expander("Advanced Options"):
        col1, col2 = st.columns(2)
        with col1:
            sync_ratings = st.checkbox("Sync ratings", value=True, key="sync_ratings")
            sync_status = st.checkbox("Sync status", value=True, key="sync_status")
        with col2:
            sync_episodes = st.checkbox("Sync episode progress", value=True, key="sync_episodes")
            sync_rewatching = st.checkbox("Sync re-watching status", value=True, key="sync_rewatching")
    
    return {
        "direction": direction,
        "options": {
            "sync_ratings": sync_ratings,
            "sync_status": sync_status,
            "sync_episodes": sync_episodes,
            "sync_rewatching": sync_rewatching
        }
    }

def sync_button_component(on_click: Callable):
    """Render sync button with loading state."""
    if st.button("🔄 Start Sync", use_container_width=True, type="primary", key="sync_button"):
        with st.spinner("Synchronizing your anime lists..."):
            on_click()

def sync_results_component(results: Dict[str, Any]):
    """Display sync results."""
    if not results:
        return
    
    st.subheader("Sync Results")
    
    # Summary stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Added", results.get("added", 0))
    with col2:
        st.metric("Updated", results.get("updated", 0))
    with col3:
        st.metric("Skipped", results.get("skipped", 0))
    
    # Detailed results
    with st.expander("View Details"):
        st.json(results)

def anime_list_component(anime_list: List[Dict[str, Any]], title: str = "Anime List"):
    """Display an anime list in a table."""
    if not anime_list:
        st.info("No anime found in this list.")
        return
    
    st.subheader(title)
    
    # Convert to DataFrame for better display
    import pandas as pd
    
    # Extract relevant fields
    data = []
    for item in anime_list:
        data.append({
            "Title": item.get("title", "N/A"),
            "Status": item.get("status", "-").title(),
            "Score": item.get("score", "-"),
            "Progress": f"{item.get('progress', 0)}/{item.get('total_episodes', '?')}",
            "Type": item.get("media_type", "-")
        })
    
    # Display as table
    df = pd.DataFrame(data)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Title": "Title",
            "Status": "Status",
            "Score": "Score",
            "Progress": "Progress",
            "Type": "Type"
        }
    )
