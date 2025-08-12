# Anime Tracker Data Sync App

A web application that helps users synchronize their anime watchlists between MyAnimeList (MAL) and AniList.

## Features

- Synchronize anime lists between MAL and AniList
- Compare lists to find intersections and differences
- Support for JSON file imports
- Real-time sync progress feedback
- Clean, minimal UI
- Rate limit handling
- Error handling and reporting

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your API credentials:
```
MAL_CLIENT_ID=your_mal_client_id
```

3. Run the application:
```bash
streamlit run app.py
```

## Usage

1. Enter your MyAnimeList and AniList usernames
2. Select the target platform for synchronization
3. Click "Sync Lists" to start the synchronization process
4. Monitor progress and view results in real-time

## Project Structure

```
backend/
├── api_clients.py     # API clients for MAL and AniList
├── anime_sync.py      # Sync manager and comparison logic
└── models.py         # Data models and schemas
app.py                # Streamlit UI
requirements.txt      # Project dependencies
README.md             # Documentation
```

## Security

- API credentials are stored in environment variables
- Rate limiting is implemented for both APIs
- Error handling is in place for API failures
- Data is normalized before comparison

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
