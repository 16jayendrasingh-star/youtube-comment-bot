"""
YouTube Data API v3 client for YouTube Auto Video Comment Bot.

Handles authentication (OAuth 2.0) and all API interactions:
- Fetching video details
- Posting comments
- Checking comment status
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube_comment_bot")


class YouTubeAPIError(Exception):
    """Custom exception for YouTube API errors."""

    def __init__(self, message: str, status_code: int = None, reason: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class YouTubeAPIClient:
    """Client for YouTube Data API v3 interactions."""

    def __init__(
        self,
        api_key: str,
        client_secrets_file: str,
        token_file: str,
        scopes: list[str],
    ):
        """
        Initialize the YouTube API client.

        Args:
            api_key: YouTube Data API key (for public read operations).
            client_secrets_file: Path to OAuth 2.0 client secrets JSON.
            token_file: Path to store/load OAuth tokens.
            scopes: OAuth scopes required.
        """
        self.api_key = api_key
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self.scopes = scopes

        self._public_service = None  # For read-only operations (API key)
        self._auth_service = None  # For write operations (OAuth)
        self._credentials = None

    def get_public_service(self):
        """Get or create the public (API key) YouTube service."""
        if self._public_service is None:
            self._public_service = build("youtube", "v3", developerKey=self.api_key)
            logger.info("YouTube public API service initialized.")
        return self._public_service

    def authenticate(self) -> bool:
        """
        Authenticate via OAuth 2.0 for write operations (posting comments).

        Returns:
            True if authentication successful, False otherwise.

        Raises:
            YouTubeAPIError: If authentication fails.
        """
        try:
            creds = None

            # Load existing token
            if os.path.exists(self.token_file):
                creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
                logger.info("Loaded existing OAuth token from %s", self.token_file)

            # Refresh or create new token
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired OAuth token...")
                    creds.refresh(Request())
                else:
                    if not os.path.exists(self.client_secrets_file):
                        raise YouTubeAPIError(
                            f"OAuth client secrets file not found: {self.client_secrets_file}. "
                            "Download it from Google Cloud Console > APIs & Credentials."
                        )
                    logger.info("Starting OAuth 2.0 authorization flow...")
                    print("\n" + "=" * 60)
                    print("AUTHENTICATION REQUIRED")
                    print("A browser window will open for Google sign-in.")
                    print("Please authorize the application to access YouTube.")
                    print("=" * 60 + "\n")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.client_secrets_file, self.scopes
                    )
                    creds = flow.run_local_server(port=0)

                # Save token for future use
                token_dir = os.path.dirname(self.token_file)
                if token_dir:
                    os.makedirs(token_dir, exist_ok=True)
                with open(self.token_file, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                logger.info("OAuth token saved to %s", self.token_file)

            self._credentials = creds
            self._auth_service = build("youtube", "v3", credentials=creds)
            logger.info("YouTube authenticated API service initialized.")
            return True

        except YouTubeAPIError:
            raise
        except Exception as e:
            raise YouTubeAPIError(f"Authentication failed: {e}") from e

    def _fetch_details_via_oembed(self, video_id: str) -> dict:
        """
        Fetch public video title and author via YouTube oEmbed service.
        Does not require an API key or credentials.

        Args:
            video_id: The YouTube video ID.

        Returns:
            Dictionary with video metadata.

        Raises:
            YouTubeAPIError: If video is deleted, private, or invalid.
        """
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        try:
            req = urllib.request.Request(
                oembed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                return {
                    "video_id": video_id,
                    "title": data.get("title", "Unknown"),
                    "channel_title": data.get("author_name", "Unknown"),
                    "description": "(Metadata fetched via public oEmbed — set API key in config/settings.yaml for full stats)",
                    "published_at": "Unknown",
                    "view_count": "N/A (API Key required)",
                    "comment_count": "N/A (API Key required)",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise YouTubeAPIError(
                    f"Video not found: {video_id}. The video may be private, deleted, or the ID is invalid.",
                    status_code=404,
                    reason="videoNotFound",
                ) from e
            raise YouTubeAPIError(
                f"Failed to fetch video details via public lookup: HTTP {e.code}",
                status_code=e.code,
            ) from e
        except Exception as e:
            raise YouTubeAPIError(
                f"Failed to fetch video details: {e}. "
                "Ensure your internet connection is active, or configure a valid API key in config/settings.yaml."
            ) from e

    def get_video_details(self, video_id: str) -> dict:
        """
        Fetch video details from YouTube.
        Tries OAuth service first, then YouTube Data API key, then falls back to public oEmbed.

        Args:
            video_id: The YouTube video ID.

        Returns:
            Dictionary with video details: title, channel, description, url.

        Raises:
            YouTubeAPIError: If the video is not found or API call fails.
        """
        # 1. Try authenticated OAuth service if already active
        if self._auth_service:
            try:
                response = (
                    self._auth_service.videos()
                    .list(part="snippet,statistics", id=video_id)
                    .execute()
                )
                if not response.get("items"):
                    raise YouTubeAPIError(
                        f"Video not found: {video_id}. The video may be private, deleted, or the ID is invalid.",
                        status_code=404,
                        reason="videoNotFound",
                    )
                item = response["items"][0]
                snippet = item["snippet"]
                stats = item.get("statistics", {})
                return {
                    "video_id": video_id,
                    "title": snippet.get("title", "Unknown"),
                    "channel_title": snippet.get("channelTitle", "Unknown"),
                    "description": snippet.get("description", "")[:200],
                    "published_at": snippet.get("publishedAt", "Unknown"),
                    "view_count": stats.get("viewCount", "N/A"),
                    "comment_count": stats.get("commentCount", "N/A"),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            except YouTubeAPIError:
                raise
            except Exception as e:
                logger.warning("OAuth video detail fetch failed: %s. Trying fallback.", e)

        # 2. Try official API key if configured
        if self.api_key and self.api_key != "YOUR_API_KEY_HERE":
            try:
                service = self.get_public_service()
                response = (
                    service.videos()
                    .list(part="snippet,statistics", id=video_id)
                    .execute()
                )

                if not response.get("items"):
                    raise YouTubeAPIError(
                        f"Video not found: {video_id}. The video may be private, deleted, or the ID is invalid.",
                        status_code=404,
                        reason="videoNotFound",
                    )

                item = response["items"][0]
                snippet = item["snippet"]
                stats = item.get("statistics", {})

                return {
                    "video_id": video_id,
                    "title": snippet.get("title", "Unknown"),
                    "channel_title": snippet.get("channelTitle", "Unknown"),
                    "description": snippet.get("description", "")[:200],
                    "published_at": snippet.get("publishedAt", "Unknown"),
                    "view_count": stats.get("viewCount", "N/A"),
                    "comment_count": stats.get("commentCount", "N/A"),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            except YouTubeAPIError:
                raise
            except HttpError as e:
                logger.warning("YouTube API key request failed (%s). Falling back to public lookup.", e)
            except Exception as e:
                logger.warning("YouTube API service error (%s). Falling back to public lookup.", e)

        # 3. Fallback to public oEmbed (zero setup / no API key needed)
        logger.info("Using public oEmbed fallback for video %s", video_id)
        return self._fetch_details_via_oembed(video_id)

    def post_comment(self, video_id: str, comment_text: str) -> dict:
        """
        Post a comment on a YouTube video.

        Requires prior authentication via authenticate().

        Args:
            video_id: The YouTube video ID.
            comment_text: The comment text to post.

        Returns:
            Dictionary with the posted comment details.

        Raises:
            YouTubeAPIError: If posting fails.
        """
        if not self._auth_service:
            raise YouTubeAPIError(
                "Not authenticated. Call authenticate() before posting comments."
            )

        try:
            body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text,
                        }
                    },
                }
            }

            response = (
                self._auth_service.commentThreads()
                .insert(part="snippet", body=body)
                .execute()
            )

            comment_id = response.get("id", "unknown")
            logger.info(
                "Comment posted successfully. ID: %s, Video: %s",
                comment_id,
                video_id,
            )

            return {
                "comment_id": comment_id,
                "video_id": video_id,
                "text": comment_text,
                "status": "posted",
            }

        except HttpError as e:
            status_code = e.resp.status if e.resp else None
            error_detail = str(e)

            if status_code == 403:
                if "commentsDisabled" in error_detail:
                    raise YouTubeAPIError(
                        "Comments are disabled on this video.",
                        status_code=403,
                        reason="commentsDisabled",
                    ) from e
                elif "quotaExceeded" in error_detail:
                    raise YouTubeAPIError(
                        "YouTube API quota exceeded. Please wait and try again later.",
                        status_code=403,
                        reason="quotaExceeded",
                    ) from e
                else:
                    raise YouTubeAPIError(
                        f"Permission denied: {error_detail}",
                        status_code=403,
                        reason="forbidden",
                    ) from e
            elif status_code == 400:
                raise YouTubeAPIError(
                    f"Bad request — comment may violate YouTube policies: {error_detail}",
                    status_code=400,
                    reason="badRequest",
                ) from e
            elif status_code == 401:
                raise YouTubeAPIError(
                    "Authentication expired. Please re-authenticate.",
                    status_code=401,
                    reason="unauthorized",
                ) from e
            else:
                raise YouTubeAPIError(
                    f"YouTube API error ({status_code}): {error_detail}",
                    status_code=status_code,
                ) from e

        except YouTubeAPIError:
            raise
        except Exception as e:
            raise YouTubeAPIError(f"Failed to post comment: {e}") from e

    def is_authenticated(self) -> bool:
        """Check if the client has valid authentication credentials."""
        return self._auth_service is not None and self._credentials is not None
