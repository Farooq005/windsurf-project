from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class AnimeEntry(BaseModel):
    title: str
    status: str
    score: Optional[int]
    episodes_watched: Optional[int]
    total_episodes: Optional[int]


class PlatformList(BaseModel):
    username: str
    anime_list: List[AnimeEntry]

class SyncConfig(BaseModel):
    mal_username: str
    anilist_username: str
    target_platform: str

class SyncDifference(BaseModel):
    """Represents the differences between two anime lists."""
    mal_only: List[AnimeEntry] = Field(default_factory=list)
    anilist_only: List[AnimeEntry] = Field(default_factory=list)
    intersection: List[AnimeEntry] = Field(default_factory=list)

class SyncResult(BaseModel):
    """Represents the result of a sync operation."""
    intersection: List[AnimeEntry] = Field(default_factory=list, description="Entries that exist in both platforms")
    differences: Dict[str, List[AnimeEntry]] = Field(default_factory=dict, description="Differences between platforms")
    success_count: int = Field(0, description="Number of successful sync operations")
    error_count: int = Field(0, description="Number of failed sync operations")
    errors: List[str] = Field(default_factory=list, description="List of error messages")
    sync_id: Optional[str] = Field(None, description="Unique identifier for this sync operation")
    timestamp: Optional[str] = Field(None, description="ISO timestamp when the sync completed")
    warnings: List[str] = Field(default_factory=list, description="List of non-critical warnings")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Additional statistics about the sync")
