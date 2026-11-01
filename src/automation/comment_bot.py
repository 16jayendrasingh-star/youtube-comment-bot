"""
Core comment bot for YouTube Auto Video Comment Bot.

Orchestrates the single-video commenting workflow:
1. User provides a YouTube video URL
2. Bot validates and locks onto that video
3. User drafts comments into a review queue
4. User explicitly approves each comment
5. Approved comments are submitted via YouTube API
6. Progress dashboard tracks all activity
"""

import time
import logging
from typing import Optional

from src.automation.video_manager import VideoManager, VideoValidationError
from src.automation.comment_queue import CommentQueue, CommentStatus
from src.automation.utils.api_client import YouTubeAPIClient, YouTubeAPIError
from src.automation.utils.config_loader import ConfigLoader

logger = logging.getLogger("youtube_comment_bot")


class CommentBot:
    """
    YouTube comment bot focused on a single target video.
    
    Provides the full workflow: target video selection, comment drafting,
    human approval, and submission with rate limiting.
    """

    def __init__(self, config: ConfigLoader):
        """
        Initialize the comment bot.

        Args:
            config: Loaded configuration.
        """
        self.config = config

        # Initialize API client
        self.api_client = YouTubeAPIClient(
            api_key=config.get("youtube_api", "api_key", default=""),
            client_secrets_file=config.get(
                "youtube_api", "client_secrets_file", default="config/client_secrets.json"
            ),
            token_file=config.get(
                "youtube_api", "token_file", default="config/token.json"
            ),
            scopes=config.get(
                "youtube_api", "scopes",
                default=["https://www.googleapis.com/auth/youtube.force-ssl"],
            ),
        )

        # Initialize managers
        self.video_manager = VideoManager(self.api_client)
        self.comment_queue = CommentQueue(
            posted_comments_file=config.get(
                "output", "posted_comments_file", default="output/posted_comments.json"
            ),
            report_file=config.get(
                "output", "report_file", default="output/report.csv"
            ),
        )

        # Rate limiting
        self._min_delay = config.get(
            "rate_limits", "min_delay_between_comments", default=30
        )
        self._max_per_session = config.get(
            "rate_limits", "max_comments_per_session", default=50
        )
        self._submitted_count = 0
        self._last_submit_time: Optional[float] = None
        self._authenticated = False

    def set_target_video(self, url_or_id: str) -> dict:
        """
        Set the target video for this session.

        Args:
            url_or_id: YouTube video URL or video ID.

        Returns:
            Video info dictionary.

        Raises:
            VideoValidationError: If URL is invalid.
            YouTubeAPIError: If video not found.
        """
        return self.video_manager.set_target_video(url_or_id)

    def authenticate(self) -> bool:
        """
        Authenticate with YouTube for comment posting.

        Returns:
            True if authentication successful.
        """
        result = self.api_client.authenticate()
        self._authenticated = result
        return result

    def add_comment(self, text: str) -> dict:
        """
        Add a comment to the review queue.

        Args:
            text: Comment text to draft.

        Returns:
            Comment info dictionary.

        Raises:
            RuntimeError: If no target video is set.
        """
        if not self.video_manager.is_set:
            raise RuntimeError("No target video set. Use set_target_video() first.")

        comment = self.comment_queue.add_comment(
            text=text,
            video_id=self.video_manager.video_id,
        )
        return comment.to_dict()

    def approve_comment(self, comment_id: int) -> dict:
        """
        Approve a pending comment.

        Args:
            comment_id: Queue ID of the comment.

        Returns:
            Updated comment dictionary.
        """
        comment = self.comment_queue.approve_comment(comment_id)
        return comment.to_dict()

    def reject_comment(self, comment_id: int) -> dict:
        """
        Reject a pending comment.

        Args:
            comment_id: Queue ID of the comment.

        Returns:
            Updated comment dictionary.
        """
        comment = self.comment_queue.reject_comment(comment_id)
        return comment.to_dict()

    def submit_approved_comments(self) -> list[dict]:
        """
        Submit all approved comments to YouTube, one at a time,
        with rate limiting between each submission.

        Returns:
            List of result dictionaries for each submission attempt.
        """
        if not self._authenticated:
            raise RuntimeError(
                "Not authenticated. Please authenticate before submitting comments."
            )

        approved = self.comment_queue.get_approved()
        if not approved:
            logger.info("No approved comments to submit.")
            return []

        results = []
        for comment in approved:
            # Check session limit
            if self._submitted_count >= self._max_per_session:
                msg = (
                    f"Session limit reached ({self._max_per_session} comments). "
                    "Please start a new session to continue."
                )
                logger.warning(msg)
                self.comment_queue.mark_failed(comment.id, msg)
                results.append({"comment_id": comment.id, "status": "failed", "error": msg})
                break

            # Rate limiting: wait if needed
            if self._last_submit_time is not None:
                elapsed = time.time() - self._last_submit_time
                if elapsed < self._min_delay:
                    wait_time = self._min_delay - elapsed
                    logger.info(
                        "Rate limit: waiting %.1f seconds before next submission...",
                        wait_time,
                    )
                    print(f"  [Rate limit] Waiting {wait_time:.0f}s before next comment...")
                    time.sleep(wait_time)

            # Submit
            try:
                logger.info("Submitting comment #%d...", comment.id)
                print(f"  Submitting comment #{comment.id}...")

                result = self.api_client.post_comment(
                    video_id=comment.video_id,
                    comment_text=comment.text,
                )

                self.comment_queue.mark_submitted(
                    comment.id, result["comment_id"]
                )
                self._submitted_count += 1
                self._last_submit_time = time.time()

                results.append({
                    "comment_id": comment.id,
                    "status": "submitted",
                    "youtube_id": result["comment_id"],
                })
                print(f"  [OK] Comment #{comment.id} posted successfully!")

            except YouTubeAPIError as e:
                error_msg = str(e)
                self.comment_queue.mark_failed(comment.id, error_msg)
                results.append({
                    "comment_id": comment.id,
                    "status": "failed",
                    "error": error_msg,
                })
                logger.error("Failed to submit comment #%d: %s", comment.id, e)
                print(f"  [FAIL] Comment #{comment.id} failed: {error_msg}")

                # Stop on auth errors — don't retry remaining
                if e.status_code in (401, 403):
                    logger.error("Stopping submissions due to auth/permission error.")
                    break

        return results

    def get_dashboard(self) -> str:
        """Get the formatted progress dashboard."""
        return self.comment_queue.display_dashboard()

    def get_queue_display(self) -> str:
        """Get the formatted comment queue listing."""
        return self.comment_queue.display_queue()

    def get_video_display(self) -> str:
        """Get the formatted target video info."""
        return self.video_manager.display_video_info()

    def save_report(self):
        """Save the session report to CSV."""
        self.comment_queue.save_report()
