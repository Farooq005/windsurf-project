import streamlit as st
from backend.anime_sync import AnimeSyncManager
from backend.api_clients import MALClient, AniListClient
from backend.models import SyncConfig
import json

# Initialize API clients
mal_client = MALClient()
anilist_client = AniListClient()

# Initialize sync manager
sync_manager = AnimeSyncManager(mal_client, anilist_client)

def main():
    st.title("Anime Tracker Data Sync")
    
    # Username inputs
    col1, col2 = st.columns(2)
    with col1:
        mal_username = st.text_input("MyAnimeList Username")
    with col2:
        anilist_username = st.text_input("AniList Username")
    
    # Target platform selection
    target_platform = st.selectbox(
        "Select Target Platform",
        ["MyAnimeList", "AniList"]
    )
    
    # JSON upload
    uploaded_file = st.file_uploader("Upload JSON file", type=["json"])
    
    # Sync button
    if st.button("Sync Lists"):
        if not mal_username or not anilist_username:
            st.error("Please provide both usernames")
            return
            
        # Create sync config
        sync_config = SyncConfig(
            mal_username=mal_username,
            anilist_username=anilist_username,
            target_platform=target_platform
        )
        
        try:
            # Start sync process
            with st.spinner("Syncing anime lists..."):
                result = sync_manager.sync_lists(sync_config)
                
            # Display results
            st.success("Sync completed!")
            st.json(result)
            
        except Exception as e:
            st.error(f"Error during sync: {str(e)}")
    
    # JSON upload processing
    if uploaded_file:
        try:
            json_data = json.load(uploaded_file)
            st.json(json_data)
            # TODO: Add JSON processing logic
        except json.JSONDecodeError:
            st.error("Invalid JSON file")

if __name__ == "__main__":
    main()
