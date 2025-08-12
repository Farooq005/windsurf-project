from pydantic import BaseModel, Field
from typing import List, Dict, Optional

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

class SyncResult(BaseModel):
    intersection: List[AnimeEntry]
    differences: Dict[str, List[AnimeEntry]]
    success_count: int
    error_count: int
    errors: List[str]
