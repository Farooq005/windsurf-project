import os
import sys
import pytest
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.api_clients import MALClient, AniListClient
from backend.anime_sync import AnimeSyncManager, SyncDirection
from backend.models import SyncConfig, AnimeEntry

# Load environment variables
load_dotenv('credentials.env')

# Test configuration
TEST_ANIME_TITLE = "Cowboy Bebop"  # A popular anime that should exist on both platforms
TEST_STATUS = "watching"
TEST_SCORE = 8
TEST_PROGRESS = 5

# Skip tests if credentials are not set
pytestmark = pytest.mark.skipif(
    not all([
        os.getenv('MAL_CLIENT_ID'),
        os.getenv('MAL_ACCESS_TOKEN'),
        os.getenv('ANILIST_ACCESS_TOKEN')
    ]),
    reason="Missing required API credentials in environment variables"
)

@pytest.fixture(scope="module")
def mal_client():
    return MALClient()

@pytest.fixture(scope="module")
def anilist_client():
    return AniListClient()

@pytest.fixture(scope="module")
def sync_manager(mal_client, anilist_client):
    return AnimeSyncManager(mal_client, anilist_client)

def test_mal_read_write(mal_client):
    """Test reading and writing to MyAnimeList."""
    # Get test anime ID
    anime_id = mal_client.search_media_id(TEST_ANIME_TITLE)
    assert anime_id is not None, f"Could not find anime: {TEST_ANIME_TITLE}"
    
    # Save entry
    success = mal_client.save_list_entry(
        title=TEST_ANIME_TITLE,
        status=TEST_STATUS,
        score=TEST_SCORE,
        progress=TEST_PROGRESS
    )
    assert success, "Failed to save entry to MAL"
    
    # Verify the entry was saved
    time.sleep(2)  # Give MAL API time to update
    user_list = mal_client.get_user_list(os.getenv('MAL_USERNAME'))
    entry = next((e for e in user_list.entries if e.title.lower() == TEST_ANIME_TITLE.lower()), None)
    assert entry is not None, "Saved entry not found in MAL list"
    assert entry.status == TEST_STATUS, f"Status mismatch. Expected {TEST_STATUS}, got {entry.status}"
    assert entry.score == TEST_SCORE, f"Score mismatch. Expected {TEST_SCORE}, got {entry.score}"
    assert entry.episodes_watched == TEST_PROGRESS, f"Progress mismatch. Expected {TEST_PROGRESS}, got {entry.episodes_watched}"

def test_anilist_read_write(anilist_client):
    """Test reading and writing to AniList."""
    # Get test anime ID
    anime_id = anilist_client.search_media_id(TEST_ANIME_TITLE)
    assert anime_id is not None, f"Could not find anime: {TEST_ANIME_TITLE}"
    
    # Save entry
    success = anilist_client.save_list_entry(
        title=TEST_ANIME_TITLE,
        status=TEST_STATUS,
        score=TEST_SCORE * 10,  # AniList uses 10-100 scale
        progress=TEST_PROGRESS
    )
    assert success, "Failed to save entry to AniList"
    
    # Verify the entry was saved
    time.sleep(2)  # Give AniList API time to update
    user_list = anilist_client.get_user_list(os.getenv('ANILIST_USERNAME'))
    entry = next((e for e in user_list.entries if e.title.lower() == TEST_ANIME_TITLE.lower()), None)
    assert entry is not None, "Saved entry not found in AniList"
    assert entry.status == TEST_STATUS, f"Status mismatch. Expected {TEST_STATUS}, got {entry.status}"
    assert entry.score == TEST_SCORE, f"Score mismatch. Expected {TEST_SCORE}, got {entry.score}"
    assert entry.episodes_watched == TEST_PROGRESS, f"Progress mismatch. Expected {TEST_PROGRESS}, got {entry.episodes_watched}"

def test_bidirectional_sync(sync_manager):
    """Test bidirectional sync between MAL and AniList."""
    # Create test sync config
    config = SyncConfig(
        mal_username=os.getenv('MAL_USERNAME'),
        anilist_username=os.getenv('ANILIST_USERNAME'),
        target_platform="MyAnimeList"
    )
    
    # Perform sync
    result = sync_manager.sync_lists(
        config=config,
        direction=SyncDirection.BIDIRECTIONAL
    )
    
    # Verify sync results
    assert result.success_count > 0, "No entries were synced"
    assert result.error_count == 0, f"Encountered {result.error_count} errors during sync"
    
    # Verify that differences were resolved
    assert not result.differences.get('mal_only', []), "Found entries only in MAL after sync"
    assert not result.differences.get('anilist_only', []), "Found entries only in AniList after sync"

if __name__ == "__main__":
    # Run tests directly for debugging
    import sys
    sys.exit(pytest.main(["-v", "--tb=short", __file__]))
