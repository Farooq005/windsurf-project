from .models import AnimeEntry, PlatformList, SyncConfig, SyncResult, JSONAnimeEntry, SyncDifference
from .api_clients import MALClient, AniListClient
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime
import logging
import random
import time
from enum import Enum
from fastapi import HTTPException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyncDirection(Enum):
    """Enum for sync direction."""
    MAL_TO_ANILIST = "mal_to_anilist"
    ANILIST_TO_MAL = "anilist_to_mal"
    BIDIRECTIONAL = "bidirectional"

class SyncStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

class AnimeSyncManager:
    """Manages the synchronization of anime lists between different platforms."""
    
    def __init__(self, mal_client: Optional[MALClient] = None, anilist_client: Optional[AniListClient] = None):
        """Initialize with optional API clients."""
        self.mal_client = mal_client or MALClient()
        self.anilist_client = anilist_client or AniListClient()
        self.sync_history: List[SyncResult] = []
        self.sync_staging = {}  # Store staging data between sync operations
        self.max_retries = 3
        self.retry_delay = 2  # Initial delay in seconds
        self.jitter = 0.5  # Random jitter factor for retry delay

        # Status mapping between platforms
        self.status_mapping = {
            "mal_to_anilist": {
                'watching': 'CURRENT',
                'completed': 'COMPLETED',
                'on_hold': 'PAUSED',
                'dropped': 'DROPPED',
                'plan_to_watch': 'PLANNING',
                '': 'PLANNING'  # Default for MAL's empty status
            },
            "anilist_to_mal": {
                'CURRENT': 'watching',
                'COMPLETED': 'completed',
                'PAUSED': 'on_hold',
                'DROPPED': 'dropped',
                'PLANNING': 'plan_to_watch',
                'REPEATING': 'watching',
                '': 'plan_to_watch'  # Default for AniList's empty status
            }
        }

    def _normalize_title(self, title: str) -> str:
        """
        Normalize anime titles for comparison.
        
        Args:
            title: The title to normalize
            
        Returns:
            str: Normalized title
        """
        if not title:
            return ""
        return title.lower().strip()
        
    def _calculate_jittered_delay(self, attempt: int) -> float:
        """
        Calculate jittered delay for retry attempts.
        
        Args:
            attempt: Current attempt number (1-based)
            
        Returns:
            float: Delay in seconds
        """
        base_delay = min(self.retry_delay * (2 ** (attempt - 1)), 30)  # Exponential backoff with max 30s
        jitter = random.uniform(1 - self.jitter, 1 + self.jitter)
        return base_delay * jitter

    def _compare_lists(self, mal_list: PlatformList, anilist_list: PlatformList) -> Dict:
        """Compare two anime lists and find differences.
        
        Args:
            mal_list: PlatformList containing MAL anime entries
            anilist_list: PlatformList containing AniList anime entries
            
        Returns:
            Dict: Dictionary containing:
                - intersection: List of anime present in both lists
                - mal_only: List of anime only in MAL list
                - anilist_only: List of anime only in AniList list
        """
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

    def _sync_to_mal(self, mal_username: str, entries: List[AnimeEntry], token: str) -> Dict:
        """
        Sync entries to MyAnimeList with retry logic.
        
        Args:
            mal_username: MAL username
            entries: List of AnimeEntry objects to sync
            token: The OAuth2 access token for MAL.

        Returns:
            Dict: Results with success/error counts and messages
        """
        success_count = 0
        errors = []
        
        for entry in entries:
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.mal_client.save_list_entry(mal_username, entry, token)
                    success_count += 1
                    break  # Success, move to next entry
                except HTTPException as e:
                    if e.status_code in [429, 500, 502, 503, 504]:
                        logger.warning(f"Attempt {attempt}/{self.max_retries} failed for {entry.title} on MAL: {e.detail}. Retrying...")
                        if attempt < self.max_retries:
                            time.sleep(self._calculate_jittered_delay(attempt))
                        else:
                            errors.append(f"Failed to sync {entry.title} to MAL after {self.max_retries} attempts: {e.detail}")
                    else:
                        errors.append(f"Error syncing {entry.title} to MAL: {e.detail}")
                        break # Non-retriable error
                except Exception as e:
                    errors.append(f"An unexpected error occurred while syncing {entry.title} to MAL: {str(e)}")
                    logger.error(f"Unexpected error syncing to MAL: {e}", exc_info=True)
                    break

        return {"success": success_count, "errors": errors}

    def _sync_to_anilist(self, anilist_username: str, entries: List[AnimeEntry], token: str) -> Dict:
        """
        Sync entries to AniList with retry logic.
        
        Args:
            anilist_username: AniList username
            entries: List of AnimeEntry objects to sync
            token: The OAuth2 access token for AniList.

        Returns:
            Dict: Results with success/error counts and messages
        """
        success_count = 0
        errors = []
        
        for entry in entries:
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.anilist_client.save_list_entry(anilist_username, entry, token)
                    success_count += 1
                    break
                except HTTPException as e:
                    if e.status_code in [429, 500, 502, 503, 504]:
                        logger.warning(f"Attempt {attempt}/{self.max_retries} failed for {entry.title} on AniList: {e.detail}. Retrying...")
                        if attempt < self.max_retries:
                            time.sleep(self._calculate_jittered_delay(attempt))
                        else:
                            errors.append(f"Failed to sync {entry.title} to AniList after {self.max_retries} attempts: {e.detail}")
                    else:
                        errors.append(f"Error syncing {entry.title} to AniList: {e.detail}")
                        break
                except Exception as e:
                    errors.append(f"An unexpected error occurred while syncing {entry.title} to AniList: {str(e)}")
                    logger.error(f"Unexpected error syncing to AniList: {e}", exc_info=True)
                    break

        return {"success": success_count, "errors": errors}

    def sync(self, config: SyncConfig, direction: SyncDirection = SyncDirection.BIDIRECTIONAL, mal_token: Optional[str] = None, anilist_token: Optional[str] = None) -> SyncResult:
        """
        Synchronize anime lists between MAL and AniList.
        
        Args:
            config: Sync configuration.
            direction: Direction of synchronization.
            mal_token: OAuth2 access token for MyAnimeList.
            anilist_token: OAuth2 access token for AniList.
            
        Returns:
            SyncResult: Result of the sync operation
            
        Raises:
            Exception: If sync fails
        """
        sync_start = datetime.utcnow()
        sync_id = f"sync_{int(sync_start.timestamp())}"
        
        if not mal_token or not anilist_token:
            raise HTTPException(status_code=401, detail="Missing one or more authentication tokens.")

        try:
            logger.info(f"Starting sync for MAL user {config.mal_username} and AniList user {config.anilist_username}")

            # Fetch lists from both platforms
            mal_list = self.mal_client.get_anime_list(config.mal_username, mal_token)
            anilist_list = self.anilist_client.get_anime_list(config.anilist_username, anilist_token)
            
            if not mal_list or not anilist_list:
                raise Exception("Failed to fetch one or both anime lists.")

            # Compare lists to find differences
            comparison = self._compare_lists(mal_list, anilist_list)
            mal_only = comparison["mal_only"]
            anilist_only = comparison["anilist_only"]

            total_success = 0
            total_errors = []

            # Sync based on direction
            if direction in [SyncDirection.BIDIRECTIONAL, SyncDirection.MAL_TO_ANILIST]:
                logger.info(f"Syncing {len(mal_only)} entries from MAL to AniList")
                if mal_only:
                    result = self._sync_to_anilist(config.anilist_username, mal_only, anilist_token)
                    total_success += result["success"]
                    total_errors.extend(result["errors"])

            if direction in [SyncDirection.BIDIRECTIONAL, SyncDirection.ANILIST_TO_MAL]:
                logger.info(f"Syncing {len(anilist_only)} entries from AniList to MAL")
                if anilist_only:
                    result = self._sync_to_mal(config.mal_username, anilist_only, mal_token)
                    total_success += result["success"]
                    total_errors.extend(result["errors"])

            sync_end = datetime.utcnow()
            sync_duration = (sync_end - sync_start).total_seconds()
            
            logger.info(f"Sync completed in {sync_duration:.2f} seconds with {total_success} successes and {len(total_errors)} errors")
            
            return SyncResult(
                intersection=comparison.get("intersection", []),
                differences={
                    "mal_only": comparison.get("mal_only", []),
                    "anilist_only": comparison.get("anilist_only", [])
                },
                success_count=total_success,
                error_count=len(total_errors),
                errors=total_errors,
                sync_id=sync_id,
                timestamp=datetime.utcnow().isoformat()
            )

        except Exception as e:
            logger.error(f"Sync failed: {str(e)}", exc_info=True)
            raise Exception(f"Sync failed: {str(e)}")

    def sync_from_json(self, json_data: List[Dict], config: SyncConfig) -> SyncResult:
        """
        Sync anime entries from JSON data with the user's structure.
        
        Args:
            json_data: List of dictionaries containing anime data
            config: Sync configuration including target platform
            
        Returns:
            SyncResult: Result of the sync operation
            
        Raises:
            Exception: If sync fails
        """
        sync_start = datetime.utcnow()
        sync_id = f"json_import_{int(sync_start.timestamp())}"
        
        try:
            logger.info(f"Starting JSON import for {len(json_data)} entries to {config.target_platform}")
            
            # Convert JSON data to AnimeEntry objects
            entries = []
            for item in json_data:
                try:
                    # Handle different JSON structures
                    if "name" in item and "mal" in item and "al" in item:
                        # New format with name, mal, al fields
                        entry = JSONAnimeEntry(
                            name=item["name"],
                            mal=item["mal"],
                            al=item["al"]
                        )
                        title = entry.name
                    elif "title" in item:
                        # Direct AnimeEntry-like format
                        title = item["title"]
                    else:
                        logger.warning(f"Skipping invalid JSON entry: {item}")
                        continue
                        
                    entries.append(AnimeEntry(
                        title=title,
                        status=item.get("status", "planning"),
                        score=item.get("score"),
                        episodes_watched=item.get("episodes_watched", 0),
                        total_episodes=item.get("total_episodes")
                    ))
                except Exception as e:
                    logger.error(f"Error processing JSON entry {item}: {str(e)}")
            
            logger.info(f"Processed {len(entries)} valid entries from JSON")
            
            # Sync based on target platform
            if config.target_platform.lower() == "myanimelist":
                result = self._sync_to_mal(config.mal_username, entries)
            else:  # AniList
                result = self._sync_to_anilist(config.anilist_username, entries)
            
            sync_end = datetime.utcnow()
            
            # Store sync history
            sync_entry = {
                "id": sync_id,
                "type": "json_import",
                "start_time": sync_start.isoformat(),
                "end_time": sync_end.isoformat(),
                "duration_seconds": (sync_end - sync_start).total_seconds(),
                "target_platform": config.target_platform,
                "entries_processed": len(entries),
                "success_count": result.get("success", 0),
                "error_count": len(result.get("errors", [])),
                "errors": result.get("errors", [])
            }
            self.sync_history.append(sync_entry)
            
            # Keep only the last 100 syncs in history
            if len(self.sync_history) > 100:
                self.sync_history = self.sync_history[-100:]
            
            logger.info(f"JSON import completed: {result.get('success', 0)} succeeded, "
                       f"{len(result.get('errors', []))} failed")
            
            return SyncResult(
                intersection=[],
                differences={"json_entries": entries},
                success_count=result.get("success", 0),
                error_count=len(result.get("errors", [])),
                errors=result.get("errors", []),
                sync_id=sync_id,
                timestamp=datetime.utcnow().isoformat()
            )

        except Exception as e:
            error_msg = f"JSON sync failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise Exception(error_msg) from e
