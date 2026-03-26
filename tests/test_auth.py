import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from sqlmodel import Session, select
from fastapi import HTTPException

from src.auth.models import Token, TokenData, UserAuth, OAuthToken
from src.auth.jwt import create_access_token, decode_access_token, SECRET_KEY, ALGORITHM
from src.auth.service import authenticate_user, get_current_user, create_user, get_user_by_provider_id, handle_oauth_callback
from src.database.models import User


# Test JWT token creation and validation
def test_create_and_decode_access_token():
    """Test JWT token creation and validation."""
    # Test data
    data = {"sub": "test_user_id", "email": "test@example.com"}
    
    # Create token
    token = create_access_token(data)
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Decode token
    token_data = decode_access_token(token)
    assert isinstance(token_data, TokenData)
    assert token_data.user_id == "test_user_id"
    assert token_data.email == "test@example.com"


def test_create_access_token_with_expiration():
    """Test JWT token creation with custom expiration."""
    # Test data
    data = {"sub": "test_user_id", "email": "test@example.com"}
    expires_delta = timedelta(minutes=15)
    
    # Create token with custom expiration
    token = create_access_token(data, expires_delta)
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Decode token
    token_data = decode_access_token(token)
    assert isinstance(token_data, TokenData)
    assert token_data.user_id == "test_user_id"
    assert token_data.email == "test@example.com"


def test_decode_invalid_token():
    """Test decoding an invalid token."""
    with pytest.raises(ValueError, match="Invalid token"):
        decode_access_token("invalid_token")


def test_decode_token_with_missing_data():
    """Test decoding a token with missing required data."""
    # Create a token with missing data
    data = {"sub": "test_user_id"}  # Missing email
    token = create_access_token(data)
    
    with pytest.raises(ValueError, match="Invalid token payload"):
        decode_access_token(token)


# Test authentication service functions
@pytest.fixture
def mock_session():
    """Mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def mock_user():
    """Mock user object."""
    return User(
        id=1,
        user_id="test_user_id",
        email="test@example.com",
        name="Test User",
        provider="google",
        profile_picture_url="https://example.com/profile.jpg"
    )


@pytest.fixture
def mock_user_auth():
    """Mock UserAuth object."""
    return UserAuth(
        user_id="test_user_id",
        email="test@example.com",
        name="Test User",
        provider="google",
        profile_picture_url="https://example.com/profile.jpg"
    )


@patch("src.auth.service.get_google_user_info")
@pytest.mark.asyncio
async def test_authenticate_user_google(mock_get_google_user_info, mock_user_auth):
    """Test authenticating a user with Google OAuth."""
    # Mock Google user info response
    mock_get_google_user_info.return_value = {
        "id": "test_user_id",
        "email": "test@example.com",
        "name": "Test User",
        "picture": "https://example.com/profile.jpg"
    }
    
    # Mock token data
    token_data = {"access_token": "test_token"}
    
    # Authenticate user
    result = await authenticate_user("google", token_data)
    
    # Verify result
    assert isinstance(result, UserAuth)
    assert result.user_id == "test_user_id"
    assert result.email == "test@example.com"
    assert result.name == "Test User"
    assert result.provider == "google"
    assert result.profile_picture_url == "https://example.com/profile.jpg"


def test_authenticate_user_unsupported_provider():
    """Test authenticating a user with an unsupported provider."""
    # Create an async function to test the coroutine
    async def test_async():
        with pytest.raises(ValueError, match="Unsupported OAuth provider: unsupported"):
            await authenticate_user("unsupported", {})
    
    # Run the async function
    import asyncio
    asyncio.run(test_async())


def test_create_user_new_user(mock_session, mock_user_auth):
    """Test creating a new user."""
    # Mock session methods
    mock_session.exec.return_value.first.return_value = None  # No existing user
    mock_session.commit.return_value = None
    mock_session.refresh.return_value = None
    
    # Create user
    result = create_user(mock_session, mock_user_auth)
    
    # Verify result
    assert isinstance(result, User)
    assert result.user_id == "test_user_id"
    assert result.email == "test@example.com"
    assert result.name == "Test User"
    assert result.provider == "google"
    assert result.profile_picture_url == "https://example.com/profile.jpg"
    
    # Verify session methods were called
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


def test_create_user_existing_user(mock_session, mock_user, mock_user_auth):
    """Test creating a user that already exists (should update)."""
    # Mock session methods
    mock_session.exec.return_value.first.return_value = mock_user  # Existing user
    mock_session.commit.return_value = None
    mock_session.refresh.return_value = None
    
    # Create user (should update existing)
    result = create_user(mock_session, mock_user_auth)
    
    # Verify result is the same user
    assert result == mock_user
    assert result.email == "test@example.com"
    assert result.name == "Test User"
    
    # Verify session methods were called
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


def test_get_user_by_provider_id(mock_session, mock_user):
    """Test getting a user by provider ID."""
    # Mock session methods
    mock_session.exec.return_value.first.return_value = mock_user
    
    # Get user
    result = get_user_by_provider_id(mock_session, "test_user_id")
    
    # Verify result
    assert result == mock_user
    assert result.user_id == "test_user_id"


def test_get_user_by_provider_id_not_found(mock_session):
    """Test getting a user by provider ID when not found."""
    # Mock session methods
    mock_session.exec.return_value.first.return_value = None
    
    # Get user
    result = get_user_by_provider_id(mock_session, "nonexistent_user_id")
    
    # Verify result
    assert result is None


@patch("src.auth.service.exchange_google_code_for_token")
@patch("src.auth.service.authenticate_user")
@patch("src.auth.service.create_user")
@patch("src.auth.service.create_access_token")
@pytest.mark.asyncio
async def test_handle_oauth_callback_google(
    mock_create_access_token,
    mock_create_user,
    mock_authenticate_user,
    mock_exchange_token,
    mock_session,
    mock_user,
    mock_user_auth
):
    """Test handling OAuth callback for Google."""
    # Mock the OAuth flow
    mock_exchange_token.return_value = {"access_token": "test_token"}
    mock_authenticate_user.return_value = mock_user_auth
    mock_create_user.return_value = mock_user
    mock_create_access_token.return_value = "test_jwt_token"
    
    # Handle OAuth callback
    result = await handle_oauth_callback("google", "test_code", mock_session)
    
    # Verify result
    assert isinstance(result, dict)
    assert "access_token" in result
    assert "token_type" in result
    assert "user" in result
    assert result["access_token"] == "test_jwt_token"
    assert result["token_type"] == "bearer"
    assert result["user"] == mock_user_auth
    
    # Verify mocks were called
    mock_exchange_token.assert_called_once_with("test_code")
    mock_authenticate_user.assert_called_once_with("google", {"access_token": "test_token"})
    mock_create_user.assert_called_once_with(mock_session, mock_user_auth)
    mock_create_access_token.assert_called_once()


def test_get_current_user_valid_token(mock_session, mock_user):
    """Test getting current user with a valid token."""
    # Mock credentials
    credentials = MagicMock()
    credentials.credentials = create_access_token(
        {"sub": "test_user_id", "email": "test@example.com"}
    )
    
    # Mock session methods
    mock_session.exec.return_value.first.return_value = mock_user
    
    # Get current user
    result = get_current_user(credentials, mock_session)
    
    # Verify result
    assert result == mock_user
    assert result.user_id == "test_user_id"


def test_get_current_user_invalid_token(mock_session):
    """Test getting current user with an invalid token."""
    # Mock credentials with invalid token
    credentials = MagicMock()
    credentials.credentials = "invalid_token"
    
    # Expect HTTPException
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials, mock_session)
    
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_user_not_found(mock_session):
    """Test getting current user when user is not found in database."""
    # Mock credentials
    credentials = MagicMock()
    credentials.credentials = create_access_token(
        {"sub": "nonexistent_user_id", "email": "test@example.com"}
    )
    
    # Mock session methods - user not found
    mock_session.exec.return_value.first.return_value = None
    
    # Expect HTTPException
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials, mock_session)
    
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_missing_data(mock_session):
    """Test getting current user with token missing required data."""
    # Mock credentials with token missing required data
    credentials = MagicMock()
    credentials.credentials = create_access_token({"sub": "test_user_id"})  # Missing email
    
    # Expect HTTPException
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials, mock_session)
    
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"