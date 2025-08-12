# Anime Tracker Data Sync App

A web application that helps users synchronize their anime watchlists between MyAnimeList (MAL) and AniList.

## Features

- Synchronize anime lists between MAL and AniList
- Compare lists to find intersections and differences
- Support for JSON file imports with custom structure
- Real-time sync progress feedback
- Clean, minimal UI
- Rate limit handling
- Error handling and reporting

## Prerequisites

- Python 3.8 or higher
- MyAnimeList API Client ID (see setup instructions below)

## Step-by-Step Setup Instructions

### 1. Clone or Download the Project
```bash
git clone <repository-url>
cd windsurf-project
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Up MyAnimeList API Credentials

#### Getting MAL Client ID:
1. Go to [MyAnimeList API](https://myanimelist.net/apiconfig)
2. Create a new application
3. Fill in the required details:
   - App Name: Your app name
   - App Type: Web
   - Description: Brief description
   - Homepage URL: http://localhost:8501 (for local testing)
   - Redirect URL: http://localhost:8501
4. Copy the Client ID from the created application

#### Creating the Credentials File:
Create a file named `credentials.env` in the project root directory:
```bash
# Windows
echo MAL_CLIENT_ID=your_actual_client_id_here > credentials.env

# Linux/Mac
echo "MAL_CLIENT_ID=your_actual_client_id_here" > credentials.env
```

**Example credentials.env file:**
```
MAL_CLIENT_ID=7d40aab44a745bbefc83c9df14413f86
```

**✅ Your credentials file is correctly formatted!** The MAL_CLIENT_ID you provided looks valid.

### 4. Verify Setup
Check that your credentials file exists and contains the correct format:
```bash
# Windows
type credentials.env

# Linux/Mac
cat credentials.env
```

You should see: `MAL_CLIENT_ID=your_client_id_here`

## Deployment Options

### Local Development/Testing

#### Method 1: Direct Streamlit Run
```bash
streamlit run app.py
```
The app will be available at: `http://localhost:8501`

#### Method 2: Custom Port
```bash
streamlit run app.py --server.port 8080
```
The app will be available at: `http://localhost:8080`

### Production Deployment

#### Streamlit Community Cloud
1. Push your code to GitHub (ensure `credentials.env` is in `.gitignore`)
2. Go to [Streamlit Community Cloud](https://streamlit.io/cloud)
3. Connect your GitHub repository
4. Add your environment variables in the Streamlit Cloud dashboard:
   - Key: `MAL_CLIENT_ID`
   - Value: `your_mal_client_id`
5. Deploy the app

#### Local Production Server
```bash
# Install additional dependencies for production
pip install gunicorn

# Run with gunicorn (if using FastAPI backend)
# For Streamlit, use:
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

## Usage

### Basic Sync Operation
1. Enter your MyAnimeList and AniList usernames
2. Select the target platform for synchronization
3. Click "Sync Lists" to start the synchronization process
4. Monitor progress and view results in real-time

### JSON File Import
1. Prepare your JSON file with the required structure (see below)
2. Enter your MAL and AniList usernames
3. Select the target platform
4. Upload your JSON file
5. Click "Process JSON File"

## JSON File Structure

The app accepts JSON files with the following structure:

```json
[
  {
    "name": "Anime/Manga Title",
    "mal": "https://myanimelist.net/manga/12345/",
    "al": "https://anilist.co/manga/67890/"
  },
  {
    "name": "Another Title",
    "mal": "https://myanimelist.net/manga/54321/",
    "al": ""
  }
]
```

### JSON Structure Details:
- **name**: The title of the anime/manga
- **mal**: MyAnimeList URL (can be empty string if not available)
- **al**: AniList URL (can be empty string if not available)

### Sample JSON File
A sample JSON file (`sample_anime_list.json`) is included in the project with example entries.

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
