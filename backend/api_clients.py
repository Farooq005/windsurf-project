import requests
from typing import List, Dict, Optional, Any
from .models import AnimeEntry, PlatformList
import time
import os
from pathlib import Path
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import HTTPException

# Load environment variables from credentials.env
loaded = load_dotenv('credentials.env')
if not loaded:
    root_env = Path(__file__).resolve().parents[1] / 'credentials.env'
    load_dotenv(root_env)

class BaseAPIClient:
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _handle_rate_limit(self, response):
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            time.sleep(retry_after)
            return True
        return False

class MALClient(BaseAPIClient):
    BASE_URL = "https://api.myanimelist.net/v2"
    
    def __init__(self):
        super().__init__()
        self.client_id = os.getenv('MAL_CLIENT_ID')
        if not self.client_id:
            raise ValueError("MAL_CLIENT_ID not found in environment variables")
        
    def get_anime_list(self, username: str, token: str) -> PlatformList:
        if not token:
            raise HTTPException(status_code=401, detail="Authentication token is required for MAL.")
            
        url = f"{self.BASE_URL}/users/{username}/animelist"
        params = {
            'fields': 'list_status,num_episodes',
            'limit': 1000,
            'nsfw': 'true'
        }
        headers = {
            'X-MAL-CLIENT-ID': self.client_id,
            'Authorization': f'Bearer {token}'
        }
        
        anime_entries: List[AnimeEntry] = []
        next_url: Optional[str] = url

        while next_url:
            response = self.session.get(next_url, params=params if next_url == url else None, headers=headers)
            if self._handle_rate_limit(response):
                time.sleep(1)
                continue
            
            response.raise_for_status()
            data = response.json()

            for node in data.get('data', []):
                anime = node.get('node', {})
                list_status = node.get('list_status', {})
                anime_entries.append(AnimeEntry(
                    title=anime.get('title', 'Unknown'),
                    status=list_status.get('status', 'unknown'),
                    score=list_status.get('score'),
                    episodes_watched=list_status.get('num_episodes_watched'),
                    total_episodes=anime.get('num_episodes')
                ))

            next_url = data.get('paging', {}).get('next')

        return PlatformList(username=username, anime_list=anime_entries)

    def search_anime_id(self, title: str) -> Optional[int]:
        url = f"{self.BASE_URL}/anime"
        params = {"q": title, "limit": 1}
        headers = {"X-MAL-CLIENT-ID": self.client_id}
        resp = self.session.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('data'):
            return None
        return data['data'][0].get('node', {}).get('id')

    def save_list_entry(self, username: str, entry: AnimeEntry, token: str) -> bool:
        if not token:
            raise HTTPException(status_code=401, detail="Authentication token is required for MAL.")

        anime_id = self.search_anime_id(entry.title)
        if not anime_id:
            raise Exception(f"MAL anime not found for title: {entry.title}")

        url = f"{self.BASE_URL}/anime/{anime_id}/my_list_status"
        data = {
            'status': entry.status,
            'score': entry.score,
            'num_episodes_watched': entry.episodes_watched
        }
        data = {k: v for k, v in data.items() if v is not None}
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        resp = self.session.put(url, headers=headers, data=data)
        resp.raise_for_status()
        return True

class AniListClient(BaseAPIClient):
    BASE_URL = "https://graphql.anilist.co"

    def get_anime_list(self, username: str, token: str) -> PlatformList:
        if not token:
            raise HTTPException(status_code=401, detail="Authentication token is required for AniList.")

        query = """
        query ($username: String) {
            MediaListCollection(userName: $username, type: ANIME) {
                lists {
                    entries {
                        status
                        score
                        progress
                        media { title { romaji } episodes }
                    }
                }
            }
        }
        """
        variables = {'username': username}
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = self.session.post(self.BASE_URL, json={'query': query, 'variables': variables}, headers=headers)
        if self._handle_rate_limit(response):
            return self.get_anime_list(username, token)
        
        response.raise_for_status()
        data = response.json()

        if data.get('errors'):
            raise Exception(f"AniList API error: {data['errors']}")
        
        collection = data.get('data', {}).get('MediaListCollection')
        if not collection:
            return PlatformList(username=username, anime_list=[])

        anime_entries: List[AnimeEntry] = []
        for lst in collection.get('lists', []):
            for entry in lst.get('entries', []):
                anime_entries.append(AnimeEntry(
                    title=entry['media']['title']['romaji'],
                    status=entry.get('status'),
                    score=entry.get('score'),
                    episodes_watched=entry.get('progress'),
                    total_episodes=entry['media'].get('episodes')
                ))

        return PlatformList(username=username, anime_list=anime_entries)

    def search_media_id(self, title: str) -> Optional[int]:
        query = 'query ($search: String) { Media(search: $search, type: ANIME) { id } }'
        variables = {"search": title}
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        resp = self.session.post(self.BASE_URL, json={"query": query, "variables": variables}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('data') or not data['data'].get('Media'):
            return None
        return data['data']['Media']['id']

    def save_list_entry(self, username: str, entry: AnimeEntry, token: str) -> bool:
        if not token:
            raise HTTPException(status_code=401, detail="Authentication token is required for AniList.")

        media_id = self.search_media_id(entry.title)
        if not media_id:
            raise Exception(f"AniList media not found for title: {entry.title}")

        mutation = '''
        mutation ($mediaId: Int!, $status: MediaListStatus, $scoreRaw: Int, $progress: Int) {
            SaveMediaListEntry(mediaId: $mediaId, status: $status, scoreRaw: $scoreRaw, progress: $progress) { id }
        }
        '''
        variables = {
            "mediaId": media_id,
            "status": entry.status,
            "scoreRaw": int(entry.score * 10) if entry.score is not None else None,
            "progress": entry.episodes_watched
        }
        variables = {k: v for k, v in variables.items() if v is not None}

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = self.session.post(self.BASE_URL, headers=headers, json={'query': mutation, 'variables': variables})
        response.raise_for_status()
        result = response.json()

        if 'errors' in result:
            raise Exception(f"AniList API errors: {result['errors']}")

        return True
