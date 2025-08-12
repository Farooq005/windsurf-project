import requests
from typing import List, Dict, Optional
from .models import AnimeEntry, PlatformList
import time
import os
from pathlib import Path
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        self.access_token = os.getenv('MAL_ACCESS_TOKEN')  # Optional; required for write
        
    def get_user_list(self, username: str) -> PlatformList:
        url = f"{self.BASE_URL}/users/{username}/animelist"
        params = {
            # Only request valid anime fields; list status is included under 'list_status'
            'fields': 'list_status,num_episodes',
            # MAL API typically maxes at 100; paginate via 'paging.next'
            'limit': 100
        }
        headers = {
            'X-MAL-CLIENT-ID': self.client_id
        }
        
        anime_entries: List[AnimeEntry] = []
        next_url: Optional[str] = url
        next_params: Optional[Dict] = params

        while next_url:
            response = self.session.get(next_url, params=next_params, headers=headers)
            if self._handle_rate_limit(response):
                # try again after waiting
                time.sleep(1)
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as e:
                # Include response text for easier debugging
                raise requests.HTTPError(f"{e} - {response.text}")

            data = response.json()

            for node in data.get('data', []):
                anime = node.get('node', {})
                list_status = node.get('list_status', {}) or {}
                score_val = list_status.get('score')
                anime_entries.append(AnimeEntry(
                    title=anime.get('title', 'Unknown'),
                    status=list_status.get('status', 'unknown'),
                    score=(int(score_val) if isinstance(score_val, (int, float)) else None),
                    episodes_watched=list_status.get('num_episodes_watched'),
                    total_episodes=anime.get('num_episodes')
                ))

            paging = data.get('paging', {})
            next_full = paging.get('next')
            if next_full:
                # When using the provided 'next' URL, don't pass params again
                next_url = next_full
                next_params = None
            else:
                next_url = None

        return PlatformList(username=username, anime_list=anime_entries)

    def _auth_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise ValueError("MAL access token missing. Set MAL_ACCESS_TOKEN in credentials.env")
        return {"Authorization": f"Bearer {self.access_token}"}

    def search_anime_id(self, title: str) -> Optional[int]:
        url = f"{self.BASE_URL}/anime"
        params = {
            "q": title,
            "limit": 1
        }
        headers = {"X-MAL-CLIENT-ID": self.client_id}
        resp = self.session.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        first = (data.get('data') or [])
        if not first:
            return None
        return first[0].get('node', {}).get('id')

    def save_list_entry(self, title: str, status: Optional[str], score: Optional[int], progress: Optional[int]) -> bool:
        anime_id = self.search_anime_id(title)
        if not anime_id:
            raise Exception(f"MAL anime not found for title: {title}")
        url = f"{self.BASE_URL}/anime/{anime_id}/my_list_status"
        data = {}
        if status:
            data["status"] = status
        if isinstance(score, (int, float)):
            # MAL expects integer 0-10
            data["score"] = int(score)
        if isinstance(progress, (int, float)):
            data["num_watched_episodes"] = int(progress)
        resp = self.session.put(url, headers=self._auth_headers(), data=data)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{e} - {resp.text}")
        return True

    def _auth_headers(self) -> Dict[str, str]:
        if not self.token:
            raise ValueError("AniList access token missing. Set ANILIST_ACCESS_TOKEN in credentials.env")
        return {"Authorization": f"Bearer {self.token}"}

    def search_media_id(self, title: str) -> Optional[int]:
        query = '''
        query ($search: String) {
          Media(search: $search, type: ANIME) { id }
        }
        '''
        variables = {"search": title}
        resp = self.session.post(self.BASE_URL, json={"query": query, "variables": variables})
        resp.raise_for_status()
        data = resp.json()
        media = (data.get('data') or {}).get('Media')
        return media.get('id') if media else None

    def save_list_entry(self, title: str, status: Optional[str], score: Optional[int], progress: Optional[int]) -> bool:
        media_id = self.search_media_id(title)
        if not media_id:
            raise Exception(f"AniList media not found for title: {title}")
        mutation = '''
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int) {
          SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress) { id }
        }
        '''
        variables = {
            "mediaId": media_id,
            "status": status,
            "score": float(score) if isinstance(score, (int, float)) else None,
            "progress": int(progress) if isinstance(progress, (int, float)) else None,
        }
        resp = self.session.post(self.BASE_URL, headers=self._auth_headers(), json={"query": mutation, "variables": variables})
        resp.raise_for_status()
        data = resp.json()
        if data.get('errors'):
            raise Exception(f"AniList mutation error: {data['errors']}")
        return True

class AniListClient(BaseAPIClient):
    BASE_URL = "https://graphql.anilist.co"
    
    def __init__(self):
        super().__init__()
        self.token = os.getenv('ANILIST_ACCESS_TOKEN')  # Optional; required for write
        
    def get_user_list(self, username: str) -> PlatformList:
        query = '''
        query ($username: String) {
            MediaListCollection(userName: $username, type: ANIME) {
                lists {
                    entries {
                        media {
                            title {
                                romaji
                            }
                            episodes
                        }
                        status
                        score
                        progress
                    }
                }
            }
        }
        '''
        
        variables = {
            'username': username
        }
        
        response = self.session.post(
            self.BASE_URL,
            json={'query': query, 'variables': variables}
        )
        
        if self._handle_rate_limit(response):
            return self.get_user_list(username)
        
        response.raise_for_status()
        data = response.json()

        # Handle GraphQL errors gracefully
        if isinstance(data, dict) and data.get('errors'):
            raise Exception(f"AniList API error: {data['errors']}")
        collection = (data.get('data') or {}).get('MediaListCollection')
        if not collection:
            return PlatformList(username=username, anime_list=[])

        anime_entries: List[AnimeEntry] = []
        for lst in (collection.get('lists') or []):
            for entry in (lst.get('entries') or []):
                score_val = entry.get('score')
                anime_entries.append(AnimeEntry(
                    title=((entry.get('media') or {}).get('title') or {}).get('romaji', 'Unknown'),
                    status=entry.get('status', 'UNKNOWN'),
                    score=(int(score_val) if isinstance(score_val, (int, float)) else None),
                    episodes_watched=entry.get('progress'),
                    total_episodes=(entry.get('media') or {}).get('episodes')
                ))

        return PlatformList(username=username, anime_list=anime_entries)
