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
        self.mal_client = mal_client
        self.anilist_client = anilist_client
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

    def _sync_to_mal(self, mal_username: str, entries: List[AnimeEntry]) -> Dict:
        """
        Sync entries to MyAnimeList with retry logic.
        
        Args:
            mal_username: MAL username
            entries: List of AnimeEntry objects to sync
            
        Returns:
            Dict: Results with success/error counts and messages
        """
        success = 0
        errors = []
        
        logger.info(f"Starting sync to MAL for {len(entries)} entries")
        
        for entry in entries:
            last_error = None
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.mal_client.save_list_entry(
                        title=entry.title,
                        status=entry.status,
                        score=entry.score,
                        progress=entry.episodes_watched,
                    )
                    success += 1
                    logger.info(f"Successfully synced '{entry.title}' to MAL")
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    last_error = str(e)
                    if attempt < self.max_retries:
                        delay = self._calculate_jittered_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt} failed for '{entry.title}'. "
                            f"Retrying in {delay:.1f}s. Error: {last_error}"
                        )
                        time.sleep(delay)
                    else:
                        error_msg = f"Failed to sync '{entry.title}' to MAL after {self.max_retries} attempts: {last_error}"
                        logger.error(error_msg)
                        errors.append(error_msg)
            
            # Be gentle with the API
            if success > 0 and success % 5 == 0:
                time.sleep(1)

        result = {
            "success": success,
            "errors": errors,
            "total_attempted": len(entries),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Completed MAL sync: {success} succeeded, {len(errors)} failed")
        return result

    def _sync_to_anilist(self, anilist_username: str, entries: List[AnimeEntry]) -> Dict:
        """
        Sync entries to AniList with retry logic.
        
        Args:
            anilist_username: AniList username
            entries: List of AnimeEntry objects to sync
            
        Returns:
            Dict: Results with success/error counts and messages
        """
        success = 0
        errors = []
        
        logger.info(f"Starting sync to AniList for {len(entries)} entries")
        
        for entry in entries:
            last_error = None
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.anilist_client.save_list_entry(
                        title=entry.title,
                        status=entry.status,
                        score=entry.score * 10 if entry.score is not None else None,  # Convert 0-10 to 0-100
                        progress=entry.episodes_watched,
                    )
                    success += 1
                    logger.info(f"Successfully synced '{entry.title}' to AniList")
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    last_error = str(e)
                    if attempt < self.max_retries:
                        delay = self._calculate_jittered_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt} failed for '{entry.title}'. "
                            f"Retrying in {delay:.1f}s. Error: {last_error}"
                        )
                        time.sleep(delay)
                    else:
                        error_msg = f"Failed to sync '{entry.title}' to AniList after {self.max_retries} attempts: {last_error}"
                        logger.error(error_msg)
                        errors.append(error_msg)
            
            # Be gentle with the API
            if success > 0 and success % 5 == 0:
                time.sleep(1)

        result = {
            "success": success,
            "errors": errors,
            "total_attempted": len(entries),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return result
    
    def sync(self, config: SyncConfig, direction: SyncDirection = SyncDirection.BIDIRECTIONAL) -> SyncResult:
        """
        Synchronize anime lists between MAL and AniList.
        
        Args:
            config: Sync configuration
            direction: Direction of synchronization
            
        Returns:
            SyncResult: Result of the sync operation
            
        Raises:
            Exception: If sync fails
        """
        sync_start = datetime.utcnow()
        sync_id = f"sync_{int(sync_start.timestamp())}"
        
        try:
            logger.info(f"Starting sync with direction: {direction.value}")
            
            # Get AniList list if needed
            anilist_list = None
            if direction in [SyncDirection.MAL_TO_ANILIST, SyncDirection.BIDIRECTIONAL]:
                try:
                    anilist_list = self.anilist_client.get_user_list()
                    logger.info(f"Fetched {len(anilist_list.anime_list) if anilist_list else 0} entries from AniList")
                except Exception as e:
                    logger.error(f"Failed to fetch AniList list: {str(e)}")
                    if direction == SyncDirection.MAL_TO_ANILIST:
                        raise Exception(f"Failed to fetch AniList list: {str(e)}")
            
            # Get MAL list if needed
            mal_list = None
            if direction in [SyncDirection.ANILIST_TO_MAL, SyncDirection.BIDIRECTIONAL]:
                try:
                    mal_list = self.mal_client.get_user_list()
                    logger.info(f"Fetched {len(mal_list.anime_list) if mal_list else 0} entries from MAL")
                except Exception as e:
                    logger.error(f"Failed to fetch MAL list: {str(e)}")
                    if direction == SyncDirection.ANILIST_TO_MAL:
                        raise Exception(f"Failed to fetch MAL list: {str(e)}")
            
            if not mal_list and not anilist_list:
                raise Exception("Failed to fetch lists from both MAL and AniList")
            
            # Compare lists if both were fetched
            comparison = self._compare_lists(
                mal_list or PlatformList(username=config.mal_username, anime_list=[]), 
                anilist_list or PlatformList(username=config.anilist_username, anime_list=[])
            )
            
            # Determine which entries to sync based on direction
            sync_results = {}
            
            # Sync from AniList to MAL
            if direction in [SyncDirection.ANILIST_TO_MAL, SyncDirection.BIDIRECTIONAL] and mal_list:
                entries_to_sync = comparison["anilist_only"]
                if entries_to_sync:
                    logger.info(f"Syncing {len(entries_to_sync)} entries from AniList to MAL")
                    sync_results["to_mal"] = self._sync_to_mal(config.mal_username, entries_to_sync)
                else:
                    logger.info("No entries to sync from AniList to MAL")
            
            # Sync from MAL to AniList
            if direction in [SyncDirection.MAL_TO_ANILIST, SyncDirection.BIDIRECTIONAL] and anilist_list:
                entries_to_sync = comparison["mal_only"]
                if entries_to_sync:
                    logger.info(f"Syncing {len(entries_to_sync)} entries from MAL to AniList")
                    sync_results["to_anilist"] = self._sync_to_anilist(config.anilist_username, entries_to_sync)
                else:
                    logger.info("No entries to sync from MAL to AniList")
            
            # Prepare sync result
            success_count = sum(r.get('success', 0) for r in sync_results.values())
            errors = []
            for result in sync_results.values():
                errors.extend(result.get('errors', []))
            
            # Store sync history
            sync_end = datetime.utcnow()
            sync_duration = (sync_end - sync_start).total_seconds()
            
            sync_entry = {
                "id": sync_id,
                "start_time": sync_start.isoformat(),
                "end_time": sync_end.isoformat(),
                "duration_seconds": sync_duration,
                "direction": direction.value,
                "success_count": success_count,
                "error_count": len(errors),
                "errors": errors,
                "config": config.dict()
            }
            self.sync_history.append(sync_entry)
            
            # Keep only the last 100 syncs in history
            if len(self.sync_history) > 100:
                self.sync_history = self.sync_history[-100:]
            
            # Store staging data
            self.sync_staging[config.target_platform] = {
                "mal_list": mal_list,
                "anilist_list": anilist_list,
                "comparison": comparison,
                "sync_result": sync_results,
                "sync_id": sync_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Sync completed in {sync_duration:.2f} seconds with {success_count} successes and {len(errors)} errors")
            
            return SyncResult(
                intersection=comparison.get("intersection", []),
                differences={
                    "mal_only": comparison.get("mal_only", []),
                    "anilist_only": comparison.get("anilist_only", [])
                },
                success_count=success_count,
                error_count=len(errors),
                errors=errors,
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
