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
        self.access_token = None
        self.username = None

    def set_credentials(self, access_token: str, username: str = None):
        """Set the access token and optionally the username for authenticated requests."""
        self.access_token = access_token
        if username:
            self.username = username

    def _handle_rate_limit(self, response):
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            time.sleep(retry_after)
            return True
        return False

    def _ensure_authenticated(self):
        """Ensure the client is properly authenticated."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="Not authenticated. Please log in first.")

class MALClient(BaseAPIClient):
    BASE_URL = "https://api.myanimelist.net/v2"
    
    def __init__(self, access_token: str = None, username: str = None):
        super().__init__()
        self.client_id = os.getenv('MAL_CLIENT_ID')
        if not self.client_id:
            raise ValueError("MAL_CLIENT_ID not found in environment variables")
        if access_token:
            self.set_credentials(access_token, username)
        
    def get_user_list(self, username: str = None) -> PlatformList:
        """
        Get the user's anime list.
        
        Args:
            username: The MAL username. If not provided, uses the authenticated user's username.
            
        Returns:
            PlatformList containing the user's anime entries
        """
        self._ensure_authenticated()
        
        if not username:
            if not self.username:
                raise ValueError("No username provided and no authenticated user set")
            username = self.username
            
        url = f"{self.BASE_URL}/users/{username}/animelist"
        params = {
            'fields': 'list_status,num_episodes',
            'limit': 1000,  # Increased limit to get all entries in one request
            'nsfw': 'true'  # Include NSFW content
        }
        
        headers = {
            'X-MAL-CLIENT-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}'
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
        """
        Save or update an anime entry in the user's MyAnimeList.
        
        Args:
            title: Title of the anime to update
            status: Watching status (watching, completed, on_hold, dropped, plan_to_watch)
            score: User's score (0-10)
            progress: Number of episodes watched
            
        Returns:
            bool: True if successful
            
        Raises:
            ValueError: If required authentication is missing
            Exception: If the anime is not found or API request fails
        """
        if not self.access_token:
            raise ValueError("MAL access token is required for write operations. Set MAL_ACCESS_TOKEN in credentials.env")
            
        anime_id = self.search_anime_id(title)
        if not anime_id:
            raise Exception(f"MAL anime not found for title: {title}")
            
        # MAL API requires at least one field to be updated
        if status is None and score is None and progress is None:
            raise ValueError("At least one of status, score, or progress must be provided")
            
        url = f"{self.BASE_URL}/anime/{anime_id}/my_list_status"
        data = {}
        
        # Map status to MAL's expected values
        status_map = {
            'watching': 'watching',
            'completed': 'completed',
            'on_hold': 'on_hold',
            'dropped': 'dropped',
            'plan_to_watch': 'plan_to_watch',
            'planning': 'plan_to_watch',
            'current': 'watching',
            'paused': 'on_hold'
        }
        
        if status:
            normalized_status = status.lower()
            data["status"] = status_map.get(normalized_status, status)
            
        if isinstance(score, (int, float)):
            # MAL expects integer 0-10
            data["score"] = min(10, max(0, int(score)))
            
        if isinstance(progress, (int, float)):
            data["num_watched_episodes"] = max(0, int(progress))
            
        headers = self._auth_headers()
        headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-MAL-Client-ID': self.client_id
        })
        
        try:
            resp = self.session.put(url, headers=headers, data=data)
            if resp.status_code == 401:
                raise Exception("Authentication failed. Please check your MAL_ACCESS_TOKEN")
            resp.raise_for_status()
            return True
        except requests.HTTPError as e:
            error_msg = f"Failed to update MAL entry for '{title}': {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg += f" - {error_data.get('message', 'No error details')}"
                except:
                    error_msg += f" - {e.response.text}"
            raise Exception(error_msg) from e
        

class AniListClient(BaseAPIClient):
    BASE_URL = "https://graphql.anilist.co"
    
    def __init__(self, access_token: str = None, username: str = None):
        super().__init__()
        if access_token:
            self.set_credentials(access_token, username)
        
    def get_user_list(self, username: str = None) -> PlatformList:
        """
        Get the user's anime list.
        
        Args:
            username: The AniList username. If not provided, uses the authenticated user's list.
            
        Returns:
            PlatformList containing the user's anime entries
        """
        self._ensure_authenticated()
        
        if not username and self.username:
            username = self.username
            
        query = """
        query ($username: String, $page: Int, $perPage: Int) {
            MediaListCollection(userName: $username, type: ANIME, sort: [MEDIA_TITLE_ENGLISH], page: $page, perPage: $perPage) {
                lists {
                    name
                    isCustomList
                    isCompletedList: isSplitCompletedList
                    entries {
                        id
                        status
                        score
                        progress
                        repeat
                        priority
                        private
                        notes
                        hiddenFromStatusLists
                        customLists
                        advancedScores
                        startedAt { year month day }
                        completedAt { year month day }
                        updatedAt
                        createdAt
                        media {
                            id
                            idMal
                            title {
                                romaji
                                english
                                native
                                userPreferred
                            }
                            type
                            format
                            status
                            description(asHtml: false)
                            startDate { year month day }
                            endDate { year month day }
                            season
                            episodes
                            duration
                            chapters
                            volumes
                            countryOfOrigin
                            isLicensed
                            source
                            hashtag
                            trailer { id site thumbnail }
                            updatedAt
                            coverImage { extraLarge large medium color }
                            bannerImage
                            genres
                            synonyms
                            averageScore
                            meanScore
                            popularity
                            trending
                            favourites
                            isAdult
                            isFavourite
                            nextAiringEpisode { airingAt timeUntilAiring episode }
                            siteUrl
                        }
                    }
                }
                user {
                    id
                    name
                    about
                    avatar { large medium }
                    bannerImage
                    isFollowing
                    isFollower
                    isBlocked
                    bans
                }
            }
        }
        """
        
        variables = {
            'username': username,
            'page': 1,
            'perPage': 1000
        }
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = self.session.post(
            self.BASE_URL,
            json={'query': query, 'variables': variables},
            headers=headers
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

    def save_list_entry(self, title: str, status: Optional[str], score: Optional[float], progress: Optional[int]) -> bool:
        """
        Save or update an anime entry in the user's AniList.
        
        Args:
            title: Title of the anime to update
            status: Watching status (CURRENT, COMPLETED, PAUSED, DROPPED, PLANNING, REPEATING)
            score: User's score (0-100)
            progress: Number of episodes watched
            
        Returns:
            bool: True if successful
            
        Raises:
            ValueError: If required authentication is missing or invalid parameters
            Exception: If the anime is not found or API request fails
        """
        if not self.token:
            raise ValueError("AniList access token is required for write operations. Set ANILIST_ACCESS_TOKEN in credentials.env")
            
        media_id = self.search_media_id(title)
        if not media_id:
            raise Exception(f"AniList media not found for title: {title}")
            
        # AniList API requires at least one field to be updated
        if status is None and score is None and progress is None:
            raise ValueError("At least one of status, score, or progress must be provided")
            
        # Map status to AniList's expected values
        status_map = {
            'watching': 'CURRENT',
            'completed': 'COMPLETED',
            'on_hold': 'PAUSED',
            'dropped': 'DROPPED',
            'plan_to_watch': 'PLANNING',
            'planning': 'PLANNING',
            'current': 'CURRENT',
            'paused': 'PAUSED',
            'repeating': 'REPEATING'
        }
        
        # Prepare variables for the mutation
        variables = {
            "mediaId": media_id,
            "status": status_map.get(status.upper()) if status else None,
            "scoreRaw": float(score) * 10 if isinstance(score, (int, float)) and score is not None else None,
            "progress": int(progress) if isinstance(progress, (int, float)) and progress is not None else None,
        }
        
        # Remove None values to avoid sending null to the API
        variables = {k: v for k, v in variables.items() if v is not None}
        
        mutation = '''
        mutation (
            $mediaId: Int!, 
            $status: MediaListStatus, 
            $scoreRaw: Int, 
            $progress: Int
        ) {
            SaveMediaListEntry(
                mediaId: $mediaId, 
                status: $status, 
                scoreRaw: $scoreRaw, 
                progress: $progress
            ) { 
                id 
                status
                progress
                score(format: POINT_10)
            }
        }
        '''
        
        headers = self._auth_headers()
        headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        try:
            response = self.session.post(
                self.BASE_URL,
                headers=headers,
                json={
                    'query': mutation,
                    'variables': variables
                },
                timeout=10
            )
            
            if response.status_code == 401:
                raise Exception("Authentication failed. Please check your ANILIST_ACCESS_TOKEN")
                
            response.raise_for_status()
            result = response.json()
            
            if 'errors' in result:
                error_messages = [err.get('message', 'Unknown error') for err in result.get('errors', [])]
                raise Exception(f"AniList API errors: {', '.join(error_messages)}")
                
            if 'data' not in result or 'SaveMediaListEntry' not in result['data']:
                raise Exception("Unexpected response format from AniList API")
                
            return True
            
        except requests.RequestException as e:
            error_msg = f"Failed to update AniList entry for '{title}': {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    if 'errors' in error_data:
                        errors = [err.get('message', 'Unknown error') for err in error_data.get('errors', [])]
                        error_msg += f" - {', '.join(errors)}"
                    else:
                        error_msg += f" - {e.response.text}"
                except:
                    error_msg += f" - {e.response.text}"
            raise Exception(error_msg) from e
