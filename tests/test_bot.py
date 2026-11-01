"""
Unit tests for the YouTube Auto Video Comment Bot.

Tests the core modules:
  - Video ID extraction and validation
  - Comment queue operations
  - Configuration loading
  - Bot orchestration

Note: These tests use mocks for YouTube API calls
      and do not make real network requests.
"""

import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.automation.video_manager import VideoManager, VideoValidationError
from src.automation.comment_queue import CommentQueue, CommentStatus, Comment
from src.automation.comment_bot import CommentBot
from src.automation.utils.config_loader import ConfigLoader
from src.automation.utils.api_client import YouTubeAPIClient, YouTubeAPIError


class TestVideoIDExtraction(unittest.TestCase):
    """Test YouTube video ID extraction from various URL formats."""

    def test_standard_url(self):
        vid = VideoManager.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_standard_url_with_extra_params(self):
        vid = VideoManager.extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120&list=PLabc"
        )
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_short_url(self):
        vid = VideoManager.extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_embed_url(self):
        vid = VideoManager.extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_shorts_url(self):
        vid = VideoManager.extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_plain_id(self):
        vid = VideoManager.extract_video_id("dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_url_without_https(self):
        vid = VideoManager.extract_video_id("youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_url_with_whitespace(self):
        vid = VideoManager.extract_video_id("  https://youtu.be/dQw4w9WgXcQ  ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_invalid_url(self):
        with self.assertRaises(VideoValidationError):
            VideoManager.extract_video_id("https://www.google.com")

    def test_empty_string(self):
        with self.assertRaises(VideoValidationError):
            VideoManager.extract_video_id("")

    def test_too_short_id(self):
        with self.assertRaises(VideoValidationError):
            VideoManager.extract_video_id("abc")

    def test_id_with_underscores_and_dashes(self):
        vid = VideoManager.extract_video_id("a_B-c1D2e3F")
        self.assertEqual(vid, "a_B-c1D2e3F")


class TestCommentQueue(unittest.TestCase):
    """Test the comment queue operations."""

    def setUp(self):
        """Create a fresh queue for each test."""
        # Reset comment ID counter
        Comment._next_id = 1
        self.queue = CommentQueue(
            posted_comments_file="test_output/posted.json",
            report_file="test_output/report.csv",
        )

    def tearDown(self):
        """Clean up test output files."""
        import shutil
        if os.path.exists("test_output"):
            shutil.rmtree("test_output")

    def test_add_comment(self):
        comment = self.queue.add_comment("Great video!", "test123")
        self.assertEqual(comment.text, "Great video!")
        self.assertEqual(comment.video_id, "test123")
        self.assertEqual(comment.status, CommentStatus.PENDING)

    def test_add_empty_comment(self):
        with self.assertRaises(ValueError):
            self.queue.add_comment("", "test123")

    def test_add_whitespace_only_comment(self):
        with self.assertRaises(ValueError):
            self.queue.add_comment("   ", "test123")

    def test_add_too_long_comment(self):
        with self.assertRaises(ValueError):
            self.queue.add_comment("x" * 10001, "test123")

    def test_approve_comment(self):
        comment = self.queue.add_comment("Nice!", "test123")
        approved = self.queue.approve_comment(comment.id)
        self.assertEqual(approved.status, CommentStatus.APPROVED)
        self.assertIsNotNone(approved.reviewed_at)

    def test_reject_comment(self):
        comment = self.queue.add_comment("Nice!", "test123")
        rejected = self.queue.reject_comment(comment.id)
        self.assertEqual(rejected.status, CommentStatus.REJECTED)

    def test_approve_non_pending(self):
        comment = self.queue.add_comment("Nice!", "test123")
        self.queue.approve_comment(comment.id)
        with self.assertRaises(ValueError):
            self.queue.approve_comment(comment.id)  # Already approved

    def test_reject_non_pending(self):
        comment = self.queue.add_comment("Nice!", "test123")
        self.queue.approve_comment(comment.id)
        with self.assertRaises(ValueError):
            self.queue.reject_comment(comment.id)  # Already approved

    def test_mark_submitted(self):
        comment = self.queue.add_comment("Nice!", "test123")
        self.queue.approve_comment(comment.id)
        submitted = self.queue.mark_submitted(comment.id, "yt_comment_123")
        self.assertEqual(submitted.status, CommentStatus.SUBMITTED)
        self.assertEqual(submitted.youtube_comment_id, "yt_comment_123")

    def test_mark_failed(self):
        comment = self.queue.add_comment("Nice!", "test123")
        failed = self.queue.mark_failed(comment.id, "API error")
        self.assertEqual(failed.status, CommentStatus.FAILED)
        self.assertEqual(failed.error_message, "API error")

    def test_get_pending(self):
        self.queue.add_comment("One", "test123")
        self.queue.add_comment("Two", "test123")
        c3 = self.queue.add_comment("Three", "test123")
        self.queue.approve_comment(c3.id)

        pending = self.queue.get_pending()
        self.assertEqual(len(pending), 2)

    def test_get_approved(self):
        c1 = self.queue.add_comment("One", "test123")
        c2 = self.queue.add_comment("Two", "test123")
        self.queue.approve_comment(c1.id)
        self.queue.approve_comment(c2.id)

        approved = self.queue.get_approved()
        self.assertEqual(len(approved), 2)

    def test_stats(self):
        c1 = self.queue.add_comment("One", "test123")
        c2 = self.queue.add_comment("Two", "test123")
        c3 = self.queue.add_comment("Three", "test123")
        self.queue.approve_comment(c1.id)
        self.queue.reject_comment(c2.id)

        stats = self.queue.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_find_nonexistent_comment(self):
        with self.assertRaises(ValueError):
            self.queue._find_comment(999)

    def test_dashboard_display(self):
        self.queue.add_comment("One", "test123")
        dashboard = self.queue.display_dashboard()
        self.assertIn("COMMENT QUEUE DASHBOARD", dashboard)
        self.assertIn("Total Comments", dashboard)

    def test_queue_display(self):
        self.queue.add_comment("One", "test123")
        display = self.queue.display_queue()
        self.assertIn("pending", display)

    def test_queue_display_empty(self):
        display = self.queue.display_queue()
        self.assertIn("empty", display.lower())

    def test_save_report(self):
        self.queue.add_comment("One", "test123")
        self.queue.save_report()
        self.assertTrue(os.path.exists("test_output/report.csv"))

    def test_save_posted_comment(self):
        comment = self.queue.add_comment("Test", "test123")
        self.queue.approve_comment(comment.id)
        self.queue.mark_submitted(comment.id, "yt_123")
        self.assertTrue(os.path.exists("test_output/posted.json"))
        with open("test_output/posted.json", "r") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["youtube_comment_id"], "yt_123")


class TestConfigLoader(unittest.TestCase):
    """Test configuration loading."""

    def test_defaults_when_no_file(self):
        config = ConfigLoader("nonexistent.yaml")
        self.assertIsNotNone(config.get("rate_limits", "min_delay_between_comments"))
        self.assertEqual(
            config.get("rate_limits", "min_delay_between_comments"), 30
        )

    def test_get_nested_value(self):
        config = ConfigLoader("nonexistent.yaml")
        val = config.get("logging", "log_level", default="INFO")
        self.assertEqual(val, "INFO")

    def test_get_with_default(self):
        config = ConfigLoader("nonexistent.yaml")
        val = config.get("nonexistent", "key", default="fallback")
        self.assertEqual(val, "fallback")


class TestCommentBotOrchestration(unittest.TestCase):
    """Test the CommentBot orchestrator with mocked API."""

    def setUp(self):
        Comment._next_id = 1
        self.config = ConfigLoader("nonexistent.yaml")
        self.bot = CommentBot(self.config)

        # Mock the API client on both the bot and the video manager
        mock_api = MagicMock(spec=YouTubeAPIClient)
        self.bot.api_client = mock_api
        self.bot.video_manager.api_client = mock_api

    def test_set_target_video(self):
        self.bot.api_client.get_video_details.return_value = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Test Video",
            "channel_title": "Test Channel",
            "description": "A test",
            "published_at": "2020-01-01",
            "view_count": "1000",
            "comment_count": "50",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }

        result = self.bot.set_target_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(result["title"], "Test Video")
        self.assertTrue(self.bot.video_manager.is_set)

    def test_add_comment_without_video(self):
        with self.assertRaises(RuntimeError):
            self.bot.add_comment("Hello!")

    def test_add_comment_with_video(self):
        # Set up video
        self.bot.api_client.get_video_details.return_value = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Test",
            "channel_title": "Test",
            "description": "",
            "published_at": "",
            "view_count": "0",
            "comment_count": "0",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        self.bot.set_target_video("dQw4w9WgXcQ")

        result = self.bot.add_comment("Great video!")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["text"], "Great video!")

    def test_approve_and_reject(self):
        self.bot.api_client.get_video_details.return_value = {
            "video_id": "test123",
            "title": "T",
            "channel_title": "C",
            "description": "",
            "published_at": "",
            "view_count": "0",
            "comment_count": "0",
            "url": "https://www.youtube.com/watch?v=test123",
        }
        self.bot.set_target_video("test1234567")

        r1 = self.bot.add_comment("Comment 1")
        r2 = self.bot.add_comment("Comment 2")

        approved = self.bot.approve_comment(r1["id"])
        self.assertEqual(approved["status"], "approved")

        rejected = self.bot.reject_comment(r2["id"])
        self.assertEqual(rejected["status"], "rejected")

    def test_submit_without_auth(self):
        self.bot._authenticated = False
        with self.assertRaises(RuntimeError):
            self.bot.submit_approved_comments()

    def test_dashboard(self):
        dashboard = self.bot.get_dashboard()
        self.assertIn("DASHBOARD", dashboard)


class TestVideoManager(unittest.TestCase):
    """Test VideoManager with mocked API."""

    def test_set_target_video_success(self):
        api_client = MagicMock(spec=YouTubeAPIClient)
        api_client.get_video_details.return_value = {
            "video_id": "abc12345678",
            "title": "Test",
            "channel_title": "Channel",
            "description": "",
            "published_at": "",
            "view_count": "100",
            "comment_count": "10",
            "url": "https://www.youtube.com/watch?v=abc12345678",
        }

        vm = VideoManager(api_client)
        info = vm.set_target_video("abc12345678")
        self.assertEqual(info["title"], "Test")
        self.assertTrue(vm.is_set)
        self.assertEqual(vm.video_id, "abc12345678")

    def test_set_target_video_not_found(self):
        api_client = MagicMock(spec=YouTubeAPIClient)
        api_client.get_video_details.side_effect = YouTubeAPIError("Not found", 404)

        vm = VideoManager(api_client)
        with self.assertRaises(YouTubeAPIError):
            vm.set_target_video("abc12345678")
        self.assertFalse(vm.is_set)

    def test_display_no_video(self):
        api_client = MagicMock(spec=YouTubeAPIClient)
        vm = VideoManager(api_client)
        display = vm.display_video_info()
        self.assertIn("No target video", display)


if __name__ == "__main__":
    unittest.main()
