"""
Comment queue for YouTube Auto Video Comment Bot.

Manages a queue of comments with human-approval workflow:
  Draft → Pending Review → Approved → Submitted
  
No comment is posted without explicit human approval.
"""

import json
import os
import csv
import logging
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("youtube_comment_bot")


class CommentStatus(Enum):
    """Status of a comment in the queue."""
    PENDING = "pending"       # Drafted, awaiting review
    APPROVED = "approved"     # Approved by user, ready to submit
    SUBMITTED = "submitted"   # Successfully posted to YouTube
    REJECTED = "rejected"     # Rejected by user
    FAILED = "failed"         # Submission attempted but failed


class Comment:
    """Represents a single comment in the queue."""

    _next_id = 1

    def __init__(self, text: str, video_id: str):
        self.id = Comment._next_id
        Comment._next_id += 1
        self.text = text
        self.video_id = video_id
        self.status = CommentStatus.PENDING
        self.created_at = datetime.now().isoformat()
        self.reviewed_at: Optional[str] = None
        self.submitted_at: Optional[str] = None
        self.youtube_comment_id: Optional[str] = None
        self.error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert comment to dictionary for serialization."""
        return {
            "id": self.id,
            "text": self.text,
            "video_id": self.video_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "submitted_at": self.submitted_at,
            "youtube_comment_id": self.youtube_comment_id,
            "error_message": self.error_message,
        }


class CommentQueue:
    """
    Manages the comment drafting, review, and submission workflow.
    
    All comments go through: Draft → Approve/Reject → Submit
    No comment is posted without explicit human approval.
    """

    def __init__(self, posted_comments_file: str = "output/posted_comments.json",
                 report_file: str = "output/report.csv"):
        """
        Initialize the comment queue.

        Args:
            posted_comments_file: Path to save posted comments JSON.
            report_file: Path to save the CSV report.
        """
        self.posted_comments_file = posted_comments_file
        self.report_file = report_file
        self._queue: list[Comment] = []

        # Ensure output directories exist
        for filepath in [posted_comments_file, report_file]:
            dirpath = os.path.dirname(filepath)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)

    def add_comment(self, text: str, video_id: str) -> Comment:
        """
        Add a new comment to the queue (status: PENDING).

        Args:
            text: The comment text.
            video_id: Target video ID.

        Returns:
            The created Comment object.
        """
        text = text.strip()
        if not text:
            raise ValueError("Comment text cannot be empty.")
        if len(text) > 10000:
            raise ValueError("Comment text exceeds YouTube's 10,000 character limit.")

        comment = Comment(text=text, video_id=video_id)
        self._queue.append(comment)
        logger.info("Comment #%d added to queue (PENDING).", comment.id)
        return comment

    def approve_comment(self, comment_id: int) -> Comment:
        """
        Approve a pending comment for submission.

        Args:
            comment_id: The comment's queue ID.

        Returns:
            The approved Comment object.

        Raises:
            ValueError: If comment not found or not in PENDING status.
        """
        comment = self._find_comment(comment_id)
        if comment.status != CommentStatus.PENDING:
            raise ValueError(
                f"Comment #{comment_id} is '{comment.status.value}', not 'pending'. "
                "Only pending comments can be approved."
            )
        comment.status = CommentStatus.APPROVED
        comment.reviewed_at = datetime.now().isoformat()
        logger.info("Comment #%d APPROVED.", comment_id)
        return comment

    def reject_comment(self, comment_id: int) -> Comment:
        """
        Reject a pending comment.

        Args:
            comment_id: The comment's queue ID.

        Returns:
            The rejected Comment object.
        """
        comment = self._find_comment(comment_id)
        if comment.status != CommentStatus.PENDING:
            raise ValueError(
                f"Comment #{comment_id} is '{comment.status.value}', not 'pending'. "
                "Only pending comments can be rejected."
            )
        comment.status = CommentStatus.REJECTED
        comment.reviewed_at = datetime.now().isoformat()
        logger.info("Comment #%d REJECTED.", comment_id)
        return comment

    def mark_submitted(self, comment_id: int, youtube_comment_id: str) -> Comment:
        """
        Mark an approved comment as successfully submitted.

        Args:
            comment_id: The comment's queue ID.
            youtube_comment_id: The YouTube-assigned comment ID.

        Returns:
            The updated Comment object.
        """
        comment = self._find_comment(comment_id)
        comment.status = CommentStatus.SUBMITTED
        comment.submitted_at = datetime.now().isoformat()
        comment.youtube_comment_id = youtube_comment_id
        logger.info(
            "Comment #%d SUBMITTED. YouTube ID: %s",
            comment_id,
            youtube_comment_id,
        )
        self._save_posted_comment(comment)
        return comment

    def mark_failed(self, comment_id: int, error_message: str) -> Comment:
        """
        Mark a comment submission as failed.

        Args:
            comment_id: The comment's queue ID.
            error_message: The error description.

        Returns:
            The updated Comment object.
        """
        comment = self._find_comment(comment_id)
        comment.status = CommentStatus.FAILED
        comment.error_message = error_message
        logger.error("Comment #%d FAILED: %s", comment_id, error_message)
        return comment

    def get_pending(self) -> list[Comment]:
        """Get all comments with PENDING status."""
        return [c for c in self._queue if c.status == CommentStatus.PENDING]

    def get_approved(self) -> list[Comment]:
        """Get all comments with APPROVED status."""
        return [c for c in self._queue if c.status == CommentStatus.APPROVED]

    def get_all(self) -> list[Comment]:
        """Get all comments in the queue."""
        return list(self._queue)

    def get_stats(self) -> dict:
        """
        Get queue statistics for the dashboard.

        Returns:
            Dictionary with counts by status and total.
        """
        stats = {
            "total": len(self._queue),
            "pending": 0,
            "approved": 0,
            "submitted": 0,
            "rejected": 0,
            "failed": 0,
        }
        for comment in self._queue:
            stats[comment.status.value] += 1
        return stats

    def display_dashboard(self) -> str:
        """
        Generate a formatted progress dashboard string.

        Returns:
            Formatted dashboard string.
        """
        stats = self.get_stats()
        lines = [
            "",
            "=" * 50,
            "  COMMENT QUEUE DASHBOARD",
            "=" * 50,
            f"  Total Comments  : {stats['total']}",
            f"  Pending Review  : {stats['pending']}",
            f"  Approved        : {stats['approved']}",
            f"  Submitted       : {stats['submitted']}",
            f"  Rejected        : {stats['rejected']}",
            f"  Failed          : {stats['failed']}",
            "=" * 50,
            "",
        ]
        return "\n".join(lines)

    def display_queue(self) -> str:
        """
        Generate a formatted display of all comments in the queue.

        Returns:
            Formatted queue listing string.
        """
        if not self._queue:
            return "\n  [Queue is empty. Use 'add' to draft a comment.]\n"

        lines = [
            "",
            "-" * 60,
            f"  {'ID':<5} {'Status':<12} {'Comment (preview)':<40}",
            "-" * 60,
        ]
        for comment in self._queue:
            preview = comment.text[:37] + "..." if len(comment.text) > 40 else comment.text
            # Replace newlines in preview
            preview = preview.replace("\n", " ")
            lines.append(
                f"  {comment.id:<5} {comment.status.value:<12} {preview:<40}"
            )
        lines.append("-" * 60)
        lines.append("")
        return "\n".join(lines)

    def _find_comment(self, comment_id: int) -> Comment:
        """Find a comment by ID or raise ValueError."""
        for comment in self._queue:
            if comment.id == comment_id:
                return comment
        raise ValueError(f"Comment #{comment_id} not found in queue.")

    def _save_posted_comment(self, comment: Comment):
        """Append a submitted comment to the posted comments JSON file."""
        try:
            existing = []
            if os.path.exists(self.posted_comments_file):
                with open(self.posted_comments_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            existing.append(comment.to_dict())

            with open(self.posted_comments_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            logger.info("Posted comment saved to %s", self.posted_comments_file)
        except Exception as e:
            logger.error("Failed to save posted comment: %s", e)

    def save_report(self):
        """Save a CSV report of all comments in the queue."""
        try:
            with open(self.report_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "id", "text", "video_id", "status",
                        "created_at", "reviewed_at", "submitted_at",
                        "youtube_comment_id", "error_message",
                    ],
                )
                writer.writeheader()
                for comment in self._queue:
                    writer.writerow(comment.to_dict())

            logger.info("Report saved to %s", self.report_file)
        except Exception as e:
            logger.error("Failed to save report: %s", e)
