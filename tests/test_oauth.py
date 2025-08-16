"""Tests for OAuth authentication."""
import pytest
from unittest.mock import patch, MagicMock
from backend.oauth_service import generate_pkce, get_authorization_url, exchange_code_for_token


def test_generate_pkce():
    """Test PKCE code generation."""
    verifier, challenge = generate_pkce()
    assert len(verifier) >= 128
    assert len(challenge) == 43


def test_get_authorization_url_mal():
    """Test MAL authorization URL generation."""
    with patch('backend.oauth_service.MAL_CLIENT_ID', 'test_client_id'), \
         patch('backend.oauth_service.MAL_REDIRECT_URI', 'http://test/callback'):
        url, verifier = get_authorization_url("mal")
        assert "https://myanimelist.net/v1/oauth2/authorize" in url
        assert "client_id=test_client_id" in url
        assert "http%3A%2F%2Ftest%2Fcallback" in url


def test_get_authorization_url_anilist():
    """Test AniList authorization URL generation."""
    with patch('backend.oauth_service.ANILIST_CLIENT_ID', 'test_client_id'), \
         patch('backend.oauth_service.ANILIST_REDIRECT_URI', 'http://test/callback'):
        url, verifier = get_authorization_url("anilist")
        assert "https://anilist.co/api/v2/oauth/authorize" in url
        assert "client_id=test_client_id" in url
        assert "http%3A%2F%2Ftest%2Fcallback" in url


def test_exchange_code_for_token_mal():
    """Test MAL token exchange."""
    with patch('requests.post') as mock_post, \
         patch('backend.oauth_service.MAL_CLIENT_ID', 'test_id'), \
         patch('backend.oauth_service.MAL_CLIENT_SECRET', 'test_secret'), \
         patch('backend.oauth_service.MAL_REDIRECT_URI', 'http://test/callback'):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test_token"}
        mock_post.return_value = mock_response
        
        token_data = exchange_code_for_token("mal", "test_code", "test_verifier")
        assert token_data["access_token"] == "test_token"


def test_exchange_code_for_token_anilist():
    """Test AniList token exchange."""
    with patch('requests.post') as mock_post, \
         patch('backend.oauth_service.ANILIST_CLIENT_ID', 'test_id'), \
         patch('backend.oauth_service.ANILIST_CLIENT_SECRET', 'test_secret'), \
         patch('backend.oauth_service.ANILIST_REDIRECT_URI', 'http://test/callback'):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test_token"}
        mock_post.return_value = mock_response
        
        token_data = exchange_code_for_token("anilist", "test_code", "test_verifier")
        assert token_data["access_token"] == "test_token"
