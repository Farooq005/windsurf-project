from .models import AnimeEntry, PlatformList, SyncConfig, SyncResult
from .api_clients import MALClient, AniListClient
from typing import List, Dict, Optional
import time

class AnimeSyncManager:
    def __init__(self, mal_client: MALClient, anilist_client: AniListClient):
        self.mal_client = mal_client
        self.anilist_client = anilist_client
        self.sync_staging = {}  # Store staging data between sync operations

    def _normalize_title(self, title: str) -> str:
        """Normalize anime titles for comparison."""
        return title.lower().strip()

    def _compare_lists(self, mal_list: PlatformList, anilist_list: PlatformList) -> Dict:
        """Compare two anime lists and find differences."""
        mal_titles = {self._normalize_title(a.title): a for a in mal_list.anime_list}
        anilist_titles = {self._normalize_title(a.title): a for a in anilist_list.anime_list}

        intersection = []
        mal_only = []
        anilist_only = []

        # Find intersection
        for title in mal_titles:
            if title in anilist_titles:
                intersection.append(mal_titles[title])

        # Find differences
        for title in mal_titles:
            if title not in anilist_titles:
                mal_only.append(mal_titles[title])

        for title in anilist_titles:
            if title not in mal_titles:
                anilist_only.append(anilist_titles[title])

        return {
            "intersection": intersection,
            "mal_only": mal_only,
            "anilist_only": anilist_only
        }

    def _sync_to_mal(self, mal_username: str, entries: List[AnimeEntry]) -> Dict:
        """Sync entries to MyAnimeList."""
        success = 0
        errors = []
        
        for entry in entries:
            try:
                # TODO: Implement MAL update logic
                # This is a placeholder for the actual MAL update API call
                success += 1
            except Exception as e:
                errors.append(f"Failed to sync {entry.title}: {str(e)}")
                time.sleep(1)  # Rate limiting

        return {"success": success, "errors": errors}

    def _sync_to_anilist(self, anilist_username: str, entries: List[AnimeEntry]) -> Dict:
        """Sync entries to AniList."""
        success = 0
        errors = []
        
        for entry in entries:
            try:
                # TODO: Implement AniList update logic
                # This is a placeholder for the actual AniList update API call
                success += 1
            except Exception as e:
                errors.append(f"Failed to sync {entry.title}: {str(e)}")
                time.sleep(1)  # Rate limiting

        return {"success": success, "errors": errors}

    def sync_lists(self, config: SyncConfig) -> SyncResult:
        """Main sync function that handles the entire sync process."""
        try:
            # Fetch lists from both platforms
            mal_list = self.mal_client.get_user_list(config.mal_username)
            anilist_list = self.anilist_client.get_user_list(config.anilist_username)

            # Compare lists
            comparison = self._compare_lists(mal_list, anilist_list)

            # Determine which entries to sync based on target platform
            if config.target_platform == "MyAnimeList":
                entries_to_sync = comparison["anilist_only"]
                result = self._sync_to_mal(config.mal_username, entries_to_sync)
            else:  # AniList
                entries_to_sync = comparison["mal_only"]
                result = self._sync_to_anilist(config.anilist_username, entries_to_sync)

            # Store staging data
            self.sync_staging[config.target_platform] = {
                "mal_list": mal_list,
                "anilist_list": anilist_list,
                "comparison": comparison,
                "sync_result": result
            }

            return SyncResult(
                intersection=comparison["intersection"],
                differences={
                    "mal_only": comparison["mal_only"],
                    "anilist_only": comparison["anilist_only"]
                },
                success_count=result["success"],
                error_count=len(result["errors"]),
                errors=result["errors"]
            )

        except Exception as e:
            raise Exception(f"Sync failed: {str(e)}")

    def sync_from_json(self, json_data: Dict, config: SyncConfig) -> SyncResult:
        """Sync anime entries from JSON data."""
        try:
            # Convert JSON data to AnimeEntry objects
            entries = []
            for item in json_data.get("anime_list", []):
                entries.append(AnimeEntry(
                    title=item["title"],
                    status=item["status"],
                    score=item.get("score"),
                    episodes_watched=item.get("episodes_watched"),
                    total_episodes=item.get("total_episodes")
                ))

            # Sync based on target platform
            if config.target_platform == "MyAnimeList":
                result = self._sync_to_mal(config.mal_username, entries)
            else:  # AniList
                result = self._sync_to_anilist(config.anilist_username, entries)

            return SyncResult(
                intersection=[],
                differences={"json_entries": entries},
                success_count=result["success"],
                error_count=len(result["errors"]),
                errors=result["errors"]
            )

        except Exception as e:
            raise Exception(f"JSON sync failed: {str(e)}")
