import requests
from typing import List, Dict, Optional
from .models import AnimeEntry, PlatformList
import time
import os
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load environment variables from credentials.env
load_dotenv('credentials.env')

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
        
    def get_user_list(self, username: str) -> PlatformList:
        url = f"{self.BASE_URL}/users/{username}/animelist"
        params = {
            'fields': 'list_status,num_episodes,status,score',
            'limit': 1000
        }
        headers = {
            'X-MAL-CLIENT-ID': self.client_id
        }
        
        response = self.session.get(url, params=params, headers=headers)
        if self._handle_rate_limit(response):
            return self.get_user_list(username)
        
        response.raise_for_status()
        data = response.json()
        
        anime_entries = []
        for node in data['data']:
            anime = node['node']
            list_status = node['list_status']
            anime_entries.append(AnimeEntry(
                title=anime['title'],
                status=list_status['status'],
                score=list_status.get('score'),
                episodes_watched=list_status.get('num_episodes_watched'),
                total_episodes=anime.get('num_episodes')
            ))
        
        return PlatformList(username=username, anime_list=anime_entries)

class AniListClient(BaseAPIClient):
    BASE_URL = "https://graphql.anilist.co"
    
    def __init__(self):
        super().__init__()
        
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
        
        anime_entries = []
        for entry in data['data']['MediaListCollection']['lists'][0]['entries']:
            anime_entries.append(AnimeEntry(
                title=entry['media']['title']['romaji'],
                status=entry['status'],
                score=entry['score'],
                episodes_watched=entry['progress'],
                total_episodes=entry['media'].get('episodes')
            ))
        
        return PlatformList(username=username, anime_list=anime_entries)
