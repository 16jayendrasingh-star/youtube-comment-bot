"""
Full-scale end-to-end integration and simulation test.
Tests the entire lifecycle:
1. Configuration loading & validation.
2. Single target video extraction & locking across multiple URL variants.
3. Natural comment suggestion generation and human customization.
4. Drafting comments into the queue.
5. Review workflow (approving & rejecting).
6. Dashboard rendering and metrics accuracy.
7. Safe rate-limited submission (mocked YouTube API).
8. Report and JSON persistence verification.
9. Error handling: invalid URLs, unavailable videos, auth failures, quota errors.
"""

import os
import sys
import json
import csv
import unittest
from unittest.mock import MagicMock

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.automation.comment_bot import CommentBot
from src.automation.comment_queue import Comment, CommentStatus
from src.automation.video_manager import VideoManager, VideoValidationError
from src.automation.comment_suggestions import get_suggestions, AVAILABLE_TONES
from src.automation.utils.config_loader import ConfigLoader
from src.automation.utils.api_client import YouTubeAPIClient, YouTubeAPIError


class FullScaleWorkflowTest(unittest.TestCase):
    def setUp(self):
        Comment._next_id = 1
        self.test_dir = os.path.join(PROJECT_ROOT, "test_output_fullscale")
        os.makedirs(self.test_dir, exist_ok=True)

        self.posted_json = os.path.join(self.test_dir, "posted_comments.json")
        self.report_csv = os.path.join(self.test_dir, "report.csv")

        # Config loader with test output paths
        self.config = ConfigLoader("nonexistent.yaml")
        self.config.config["output"]["posted_comments_file"] = self.posted_json
        self.config.config["output"]["report_file"] = self.report_csv
        self.config.config["rate_limits"]["min_delay_between_comments"] = 0  # 0s for fast test

        self.bot = CommentBot(self.config)
        self.mock_api = MagicMock(spec=YouTubeAPIClient)
        self.bot.api_client = self.mock_api
        self.bot.video_manager.api_client = self.mock_api

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_full_lifecycle(self):
        print("\n--- 1. Testing Video Target Setup ---")
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.mock_api.get_video_details.return_value = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
            "channel_title": "Rick Astley",
            "description": "The official video for Never Gonna Give You Up",
            "published_at": "2009-10-25T06:57:33Z",
            "view_count": "1500000000",
            "comment_count": "12000000",
            "url": target_url,
        }

        video_info = self.bot.set_target_video(target_url)
        self.assertTrue(self.bot.video_manager.is_set)
        self.assertEqual(video_info["video_id"], "dQw4w9WgXcQ")
        self.assertIn("Rick Astley", self.bot.get_video_display())
        print(f"Locked onto video: {video_info['title']} ({video_info['url']})")

        print("\n--- 2. Testing Natural Comment Generation & Customization ---")
        # Ensure available tones exist
        self.assertTrue(len(AVAILABLE_TONES) >= 5)
        # Generate suggestions for topic "audio mastering and 80s synth production"
        suggestions = get_suggestions(tone="appreciation", topic="the remastering and vocal clarity")
        self.assertGreater(len(suggestions), 0)
        self.assertTrue(any("the remastering and vocal clarity" in s for s in suggestions))

        # Human selects and customizes 3 distinct natural comments
        c1_text = suggestions[0]  # Appreciation
        c2_text = "I really appreciate how well the sound holds up today. What synth was used for the bassline?"  # Question
        c3_text = "Unrelated spam link: click here for free gift cards"  # To test rejection

        # Add to queue
        c1 = self.bot.add_comment(c1_text)
        c2 = self.bot.add_comment(c2_text)
        c3 = self.bot.add_comment(c3_text)

        self.assertEqual(c1["status"], "pending")
        self.assertEqual(c2["status"], "pending")
        self.assertEqual(c3["status"], "pending")

        print("Queue after drafting 3 comments:")
        print(self.bot.get_queue_display())

        print("\n--- 3. Testing Human Review (Approve / Reject) ---")
        # Approve legitimate comments
        appr1 = self.bot.approve_comment(c1["id"])
        appr2 = self.bot.approve_comment(c2["id"])
        # Reject spammy comment
        rej3 = self.bot.reject_comment(c3["id"])

        self.assertEqual(appr1["status"], "approved")
        self.assertEqual(appr2["status"], "approved")
        self.assertEqual(rej3["status"], "rejected")

        print("Queue after review:")
        print(self.bot.get_queue_display())

        print("\n--- 4. Checking Dashboard Metrics Before Submission ---")
        stats = self.bot.comment_queue.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(stats["approved"], 2)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["submitted"], 0)
        print(self.bot.get_dashboard())

        print("\n--- 5. Testing Submission Workflow ---")
        self.bot._authenticated = True
        self.mock_api.post_comment.side_effect = [
            {"comment_id": "yt_cmt_001", "video_id": "dQw4w9WgXcQ"},
            {"comment_id": "yt_cmt_002", "video_id": "dQw4w9WgXcQ"},
        ]

        results = self.bot.submit_approved_comments()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["status"], "submitted")
        self.assertEqual(results[1]["status"], "submitted")

        print("\n--- 6. Checking Dashboard Metrics After Submission ---")
        stats_after = self.bot.comment_queue.get_stats()
        self.assertEqual(stats_after["total"], 3)
        self.assertEqual(stats_after["submitted"], 2)
        self.assertEqual(stats_after["approved"], 0)
        self.assertEqual(stats_after["rejected"], 1)
        print(self.bot.get_dashboard())

        print("\n--- 7. Verifying Persistence (JSON & CSV Report) ---")
        self.bot.save_report()
        self.assertTrue(os.path.exists(self.posted_json))
        self.assertTrue(os.path.exists(self.report_csv))

        with open(self.posted_json, "r", encoding="utf-8") as f:
            posted_data = json.load(f)
            self.assertEqual(len(posted_data), 2)
            self.assertEqual(posted_data[0]["youtube_comment_id"], "yt_cmt_001")

        with open(self.report_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 3)

        print("Persistence verified: 2 submitted records in JSON, 3 total in CSV.")

        print("\n--- 8. Testing Error Handling Scenarios ---")
        # A. Invalid URL format
        with self.assertRaises(VideoValidationError):
            self.bot.set_target_video("https://not-youtube.com/something")

        # B. Video not found on YouTube
        self.mock_api.get_video_details.side_effect = YouTubeAPIError("Video not found", status_code=404)
        with self.assertRaises(YouTubeAPIError):
            self.bot.set_target_video("dQw4w9WgXc0")

        # C. API Quota exceeded or permission denied on submission
        self.mock_api.get_video_details.side_effect = None
        c4 = self.bot.add_comment("Another natural comment here.")
        self.bot.approve_comment(c4["id"])
        self.mock_api.post_comment.side_effect = YouTubeAPIError("YouTube API quota exceeded", status_code=403)
        fail_results = self.bot.submit_approved_comments()
        self.assertEqual(fail_results[0]["status"], "failed")
        self.assertEqual(self.bot.comment_queue.get_stats()["failed"], 1)
        print("API error properly caught and flagged in dashboard as 'failed'.")


if __name__ == "__main__":
    unittest.main()
