"""
Video manager for YouTube Auto Video Comment Bot.

Handles video URL parsing, validation, and fetching video
information. Ensures the bot stays focused on a single target video.
"""

import re
import logging
from typing import Optional

from src.automation.utils.api_client import YouTubeAPIClient, YouTubeAPIError

logger = logging.getLogger("youtube_comment_bot")

# Regex patterns for extracting YouTube video IDs from various URL formats
YOUTUBE_URL_PATTERNS = [
    # Standard: https://www.youtube.com/watch?v=VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})"),
    # Short: https://youtu.be/VIDEO_ID
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})"),
    # Embed: https://www.youtube.com/embed/VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
    # Shorts: https://www.youtube.com/shorts/VIDEO_ID
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    # Plain video ID (11 characters, alphanumeric + _ -)
    re.compile(r"^([a-zA-Z0-9_-]{11})$"),
]


class VideoValidationError(Exception):
    """Raised when a video URL or ID is invalid."""
    pass


class VideoManager:
    """
    Manages the single target video for the bot session.
    
    Extracts and validates video IDs from URLs, fetches video
    information, and keeps the bot locked onto one video.
    """

    def __init__(self, api_client: YouTubeAPIClient):
        """
        Initialize the video manager.

        Args:
            api_client: Configured YouTube API client.
        """
        self.api_client = api_client
        self._video_id: Optional[str] = None
        self._video_info: Optional[dict] = None

    @staticmethod
    def extract_video_id(url_or_id: str) -> str:
        """
        Extract a YouTube video ID from a URL or plain ID string.

        Supports formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://www.youtube.com/shorts/VIDEO_ID
        - Plain 11-character video ID

        Args:
            url_or_id: YouTube URL or video ID.

        Returns:
            The 11-character video ID.

        Raises:
            VideoValidationError: If no valid video ID can be extracted.
        """
        url_or_id = url_or_id.strip()

        if not url_or_id:
            raise VideoValidationError("Empty URL or video ID provided.")

        for pattern in YOUTUBE_URL_PATTERNS:
            match = pattern.search(url_or_id)
            if match:
                video_id = match.group(1)
                logger.info("Extracted video ID: %s from input: %s", video_id, url_or_id)
                return video_id

        raise VideoValidationError(
            f"Could not extract a valid YouTube video ID from: '{url_or_id}'\n"
            "Supported formats:\n"
            "  - https://www.youtube.com/watch?v=VIDEO_ID\n"
            "  - https://youtu.be/VIDEO_ID\n"
            "  - https://www.youtube.com/embed/VIDEO_ID\n"
            "  - https://www.youtube.com/shorts/VIDEO_ID\n"
            "  - Plain 11-character video ID"
        )

    def set_target_video(self, url_or_id: str) -> dict:
        """
        Set the target video for this session.

        Extracts the video ID, validates it against the YouTube API,
        and stores the video information.

        Args:
            url_or_id: YouTube URL or video ID.

        Returns:
            Dictionary with video details.

        Raises:
            VideoValidationError: If URL is invalid.
            YouTubeAPIError: If video not found or API error.
        """
        video_id = self.extract_video_id(url_or_id)

        logger.info("Validating video ID against YouTube API: %s", video_id)
        video_info = self.api_client.get_video_details(video_id)

        self._video_id = video_id
        self._video_info = video_info

        logger.info(
            "Target video set: '%s' (ID: %s)",
            video_info["title"],
            video_id,
        )

        return video_info

    @property
    def video_id(self) -> Optional[str]:
        """Get the current target video ID."""
        return self._video_id

    @property
    def video_info(self) -> Optional[dict]:
        """Get the current target video's information."""
        return self._video_info

    @property
    def is_set(self) -> bool:
        """Check if a target video has been set."""
        return self._video_id is not None

    def display_video_info(self) -> str:
        """
        Generate a formatted display string for the target video.

        Returns:
            Formatted string with video details.
        """
        if not self._video_info:
            return "No target video selected."

        info = self._video_info
        lines = [
            "",
            "=" * 60,
            "  TARGET VIDEO",
            "=" * 60,
            f"  Title   : {info['title']}",
            f"  Channel : {info['channel_title']}",
            f"  URL     : {info['url']}",
            f"  Views   : {info['view_count']}",
            f"  Comments: {info['comment_count']}",
            f"  Posted  : {info['published_at']}",
            "=" * 60,
            "",
        ]
        return "\n".join(lines)
