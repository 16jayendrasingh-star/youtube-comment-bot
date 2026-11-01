"""
YouTube Auto Video Comment Bot — Main Entry Point

Interactive CLI for the single-video YouTube comment bot.
Provides a command-based interface for:
  - Setting a target video
  - Drafting comments
  - Reviewing and approving/rejecting comments
  - Submitting approved comments
  - Viewing the progress dashboard
"""

import sys
import os

# Ensure console supports UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is on sys.path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from colorama import init as colorama_init, Fore, Style

from src.automation.comment_bot import CommentBot
from src.automation.video_manager import VideoValidationError
from src.automation.utils.api_client import YouTubeAPIError
from src.automation.utils.config_loader import ConfigLoader
from src.automation.utils.logger import setup_logger
from src.automation.comment_suggestions import get_suggestions, get_tones_display, AVAILABLE_TONES


# ── Constants ──────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║        YouTube Auto Video Comment Bot                        ║
║        Single-Video Targeting Mode                           ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Available Commands:
───────────────────────────────────────────────────────────────
  video <URL>       Set the target YouTube video
  info              Show target video details
  auth              Authenticate with YouTube (OAuth 2.0)

  add               Draft a new comment (multi-line supported)
  suggest [tone] [topic]  Get natural comment suggestions
  tones             Show available comment tones
  queue             Show all comments in the queue
  view <ID>         View full text of a comment
  edit <ID>         Edit a pending comment
  approve <ID>      Approve a pending comment
  reject <ID>       Reject a pending comment

  submit            Submit all approved comments to YouTube
  dashboard         Show progress dashboard

  report            Save session report to CSV
  help              Show this help message
  quit / exit       Exit the bot
───────────────────────────────────────────────────────────────
"""


def safe_str(text: str) -> str:
    """Ensure string is safe to print on any console encoding."""
    encoding = sys.stdout.encoding or "utf-8"
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, errors="replace").decode(encoding)


def print_colored(text: str, color=Fore.WHITE):
    """Print colored text to console."""
    print(f"{color}{safe_str(text)}{Style.RESET_ALL}")


def print_error(text: str):
    """Print an error message."""
    print(f"{Fore.RED}  [ERROR] {safe_str(text)}{Style.RESET_ALL}")


def print_success(text: str):
    """Print a success message."""
    print(f"{Fore.GREEN}  [OK] {safe_str(text)}{Style.RESET_ALL}")


def print_warning(text: str):
    """Print a warning message."""
    print(f"{Fore.YELLOW}  [WARNING] {safe_str(text)}{Style.RESET_ALL}")


def read_multiline_input(prompt: str = "  (Enter comment text. Type END on a new line to finish)") -> str:
    """
    Read multi-line input from the user until they type END on its own line.

    Args:
        prompt: Instruction prompt to display.

    Returns:
        The concatenated multi-line string.
    """
    print(prompt)
    lines = []
    while True:
        try:
            line = input("  > ")
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def main():
    """Main entry point for the YouTube comment bot CLI."""
    colorama_init()

    print(Fore.CYAN + BANNER + Style.RESET_ALL)

    # Load configuration
    config_path = os.path.join(PROJECT_ROOT, "config", "settings.yaml")
    config = ConfigLoader(config_path)

    # Setup logger
    log_file = config.get("logging", "log_file", default="logs/activity.log")
    log_level = config.get("logging", "log_level", default="INFO")
    logger = setup_logger(
        log_file=os.path.join(PROJECT_ROOT, log_file),
        log_level=log_level,
    )

    # Validate configuration
    issues = config.validate()
    if issues:
        print_warning("Configuration issues detected:")
        for issue in issues:
            print_warning(f"  • {issue}")
        print()

    # Initialize bot
    bot = CommentBot(config)

    print(HELP_TEXT)

    # ── Main command loop ──────────────────────────────────────────────────

    while True:
        try:
            raw_input_str = input(f"{Fore.CYAN}bot> {Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not raw_input_str:
            continue

        parts = raw_input_str.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # ── Video commands ─────────────────────────────────────────────────

        if command == "video":
            if not arg:
                print_error("Usage: video <YouTube URL or video ID>")
                continue
            try:
                video_info = bot.set_target_video(arg)
                print_success("Target video set!")
                print(safe_str(bot.get_video_display()))
            except VideoValidationError as e:
                print_error(str(e))
            except YouTubeAPIError as e:
                print_error(str(e))

        elif command == "info":
            print(safe_str(bot.get_video_display()))

        # ── Authentication ─────────────────────────────────────────────────

        elif command == "auth":
            try:
                if bot.authenticate():
                    print_success("Authenticated with YouTube successfully!")
                else:
                    print_error("Authentication failed.")
            except YouTubeAPIError as e:
                print_error(str(e))

        # ── Comment drafting ───────────────────────────────────────────────

        elif command == "add":
            if not bot.video_manager.is_set:
                print_error("Set a target video first: video <URL>")
                continue

            if arg:
                comment_text = arg
            else:
                comment_text = read_multiline_input()

            if not comment_text.strip():
                print_warning("Empty comment — not added.")
                continue

            try:
                result = bot.add_comment(comment_text)
                print_success(
                    f"Comment #{result['id']} added to queue (status: pending)."
                )
            except ValueError as e:
                print_error(str(e))
            except RuntimeError as e:
                print_error(str(e))

        elif command == "queue":
            print(safe_str(bot.get_queue_display()))

        elif command == "view":
            if not arg or not arg.isdigit():
                print_error("Usage: view <comment ID>")
                continue
            try:
                comment = bot.comment_queue._find_comment(int(arg))
                print(f"\n  Comment #{comment.id}")
                print(f"  Status: {comment.status.value}")
                print(f"  Created: {comment.created_at}")
                print(f"  Text:")
                for line in comment.text.split("\n"):
                    print(f"    {line}")
                print()
            except ValueError as e:
                print_error(str(e))

        elif command == "suggest":
            if not bot.video_manager.is_set:
                print_error("Set a target video first: video <URL>")
                continue

            parts_suggest = arg.split(maxsplit=1) if arg else []
            tone = parts_suggest[0] if parts_suggest and parts_suggest[0] in AVAILABLE_TONES else None
            topic = parts_suggest[1] if len(parts_suggest) > 1 else ""
            if parts_suggest and not tone:
                # If first word isn't a tone, treat entire arg as topic
                topic = arg
                tone = None

            suggestions = get_suggestions(tone=tone, topic=topic)
            print(f"\n  {'-' * 55}")
            print(f"  Comment Suggestions{f' (tone: {tone})' if tone else ' (mixed)'}:")
            print(f"  {'-' * 55}")
            for i, s in enumerate(suggestions, 1):
                print(f"  {i}. {s}")
            print(f"  {'-' * 55}")
            print("  -> To use one: type 'pick <number>' to add it to queue")
            print("  -> Or type 'add' to write your own\n")

            # Store suggestions for quick-pick
            bot._last_suggestions = suggestions

        elif command == "pick":
            if not hasattr(bot, '_last_suggestions') or not bot._last_suggestions:
                print_error("No suggestions to pick from. Run 'suggest' first.")
                continue
            if not arg or not arg.isdigit():
                print_error("Usage: pick <suggestion number>")
                continue
            idx = int(arg) - 1
            if idx < 0 or idx >= len(bot._last_suggestions):
                print_error(f"Pick a number between 1 and {len(bot._last_suggestions)}")
                continue

            picked = bot._last_suggestions[idx]
            print(f"\n  Selected: {picked}")
            if "[your specific detail here]" in picked:
                print_warning("This comment has a placeholder. Let's personalize it.")
                detail = input("  Enter the specific detail to fill in: ").strip()
                if detail:
                    picked = picked.replace("[your specific detail here]", detail)
                    print_success(f"Updated: {picked}")

            # Let user edit before adding
            edit_choice = input("  Edit before adding? (yes/no): ").strip().lower()
            if edit_choice in ("yes", "y"):
                print("  Enter your edited comment (type END on a new line to finish):")
                edited = read_multiline_input("  (Edit the comment. Type END to finish)")
                if edited.strip():
                    picked = edited

            try:
                result = bot.add_comment(picked)
                print_success(f"Comment #{result['id']} added to queue (status: pending).")
            except (ValueError, RuntimeError) as e:
                print_error(str(e))

        elif command == "tones":
            print(get_tones_display())

        elif command == "edit":
            if not arg or not arg.isdigit():
                print_error("Usage: edit <comment ID>")
                continue
            try:
                comment = bot.comment_queue._find_comment(int(arg))
                if comment.status.value != "pending":
                    print_error(f"Comment #{comment.id} is '{comment.status.value}'. Only pending comments can be edited.")
                    continue
                print(f"\n  Current text of comment #{comment.id}:")
                for line in comment.text.split("\n"):
                    print(f"    {line}")
                print()
                new_text = read_multiline_input("  (Enter new text. Type END to finish)")
                if new_text.strip():
                    comment.text = new_text.strip()
                    print_success(f"Comment #{comment.id} updated.")
                else:
                    print_warning("Empty text — comment not changed.")
            except ValueError as e:
                print_error(str(e))

        # ── Review commands ────────────────────────────────────────────────

        elif command == "approve":
            if not arg or not arg.isdigit():
                print_error("Usage: approve <comment ID>")
                continue
            try:
                result = bot.approve_comment(int(arg))
                print_success(f"Comment #{result['id']} approved!")
            except ValueError as e:
                print_error(str(e))

        elif command == "reject":
            if not arg or not arg.isdigit():
                print_error("Usage: reject <comment ID>")
                continue
            try:
                result = bot.reject_comment(int(arg))
                print_success(f"Comment #{result['id']} rejected.")
            except ValueError as e:
                print_error(str(e))

        # ── Submission ─────────────────────────────────────────────────────

        elif command == "submit":
            approved = bot.comment_queue.get_approved()
            if not approved:
                print_warning("No approved comments to submit. Approve some first.")
                continue

            if not bot.api_client.is_authenticated():
                print_error("Not authenticated. Run 'auth' first.")
                continue

            print(f"\n  About to submit {len(approved)} approved comment(s).")
            print("  Rate limiting is active between submissions.\n")

            confirm = input(f"  Proceed? (yes/no): ").strip().lower()
            if confirm not in ("yes", "y"):
                print_warning("Submission cancelled.")
                continue

            results = bot.submit_approved_comments()
            print(f"\n  Submission complete. {len(results)} comment(s) processed.")
            print(bot.get_dashboard())

        # ── Dashboard ──────────────────────────────────────────────────────

        elif command == "dashboard":
            print(safe_str(bot.get_video_display()))
            print(safe_str(bot.get_dashboard()))

        # ── Report ─────────────────────────────────────────────────────────

        elif command == "report":
            bot.save_report()
            print_success(
                f"Report saved to {bot.comment_queue.report_file}"
            )

        # ── Help / Exit ────────────────────────────────────────────────────

        elif command == "help":
            print(HELP_TEXT)

        elif command in ("quit", "exit"):
            # Save report on exit
            if bot.comment_queue.get_all():
                bot.save_report()
                print_success("Session report saved.")
            print("\nGoodbye!\n")
            break

        else:
            print_error(f"Unknown command: '{command}'. Type 'help' for available commands.")


if __name__ == "__main__":
    main()
