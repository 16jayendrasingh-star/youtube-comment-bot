"""
Natural comment suggestions for YouTube Auto Video Comment Bot.

Provides context-aware, human-sounding comment templates based on
video category/topic. These are SUGGESTIONS — the user reviews,
edits, and approves every comment before it's posted.

No spintax, no randomized evasion. Just natural starting points
that the user customizes to be genuine.
"""

# Comment templates organized by video category/tone.
# Each template is a natural-sounding starting point.
# The user should ALWAYS personalize these before approving.

COMMENT_TEMPLATES = {
    "appreciation": [
        "This was really well put together. The part about {topic} really stood out to me.",
        "I've been looking for a video that explains {topic} this clearly. Thanks for making this.",
        "Just finished watching the whole thing — the quality of this content is impressive.",
        "This deserves way more views. The effort you put into this really shows.",
        "I keep coming back to this video. It's one of the best explanations of {topic} I've found.",
    ],
    "question": [
        "Great video! I'm curious — what are your thoughts on {topic}?",
        "This was super helpful. Do you have any plans to make a follow-up covering {topic}?",
        "Love the content. One thing I was wondering — how did you approach {topic}?",
        "Really enjoyed this. Could you go deeper into {topic} in a future video?",
        "Thanks for sharing this. Quick question — what resources would you recommend for learning more about {topic}?",
    ],
    "personal_experience": [
        "I actually tried this myself and {topic} was the game changer for me.",
        "This reminds me of when I first started learning about {topic}. Wish I had this video back then.",
        "Been doing this for a while now and I can confirm — {topic} makes a huge difference.",
        "I was skeptical at first but after watching this and trying it out, {topic} really works.",
        "As someone who works with {topic} daily, this video nails the key points.",
    ],
    "constructive": [
        "Solid video overall. It might also be worth mentioning {topic} for a more complete picture.",
        "Great content as always. One small thing — it would be helpful to also cover {topic}.",
        "Really enjoyed this. A follow-up that dives into {topic} would be awesome.",
        "Nice breakdown. I think your audience would also benefit from hearing about {topic}.",
        "Good stuff. Adding timestamps in the description would make it even easier to navigate.",
    ],
    "supportive": [
        "Just subscribed. This kind of content is exactly what YouTube needs more of.",
        "The production quality here is seriously underrated. Keep it up!",
        "I shared this with a few friends — they all loved it too.",
        "You've clearly done your research on this. The depth of information is really appreciated.",
        "This channel is becoming one of my go-to sources for {topic}. Consistently great work.",
    ],
}

# Tones available
AVAILABLE_TONES = list(COMMENT_TEMPLATES.keys())


def get_suggestions(tone: str = None, topic: str = "") -> list[str]:
    """
    Get natural comment suggestions for the given tone.

    Args:
        tone: One of 'appreciation', 'question', 'personal_experience',
              'constructive', 'supportive'. If None, returns mix of all.
        topic: Optional topic to fill into templates. If empty,
               the {topic} placeholder is replaced with a reminder.

    Returns:
        List of comment suggestion strings.
    """
    placeholder = topic if topic else "[your specific detail here]"

    if tone and tone in COMMENT_TEMPLATES:
        templates = COMMENT_TEMPLATES[tone]
    else:
        # Mix: pick one from each category
        templates = []
        for category_templates in COMMENT_TEMPLATES.values():
            templates.append(category_templates[0])

    return [t.replace("{topic}", placeholder) for t in templates]


def get_tones_display() -> str:
    """
    Get a formatted display of available comment tones.

    Returns:
        Formatted string listing all tones with descriptions.
    """
    descriptions = {
        "appreciation": "Genuine praise and positive feedback",
        "question": "Thoughtful questions to start a conversation",
        "personal_experience": "Relatable personal stories and experiences",
        "constructive": "Helpful suggestions and constructive feedback",
        "supportive": "Encouragement and community support",
    }

    lines = [
        "",
        "  Available Comment Tones:",
        "  " + "-" * 50,
    ]
    for tone, desc in descriptions.items():
        lines.append(f"    {tone:<25} {desc}")
    lines.append("  " + "-" * 50)
    lines.append("")
    lines.append("  Usage: suggest <tone> [topic]")
    lines.append("  Example: suggest appreciation machine learning")
    lines.append("  Example: suggest question")
    lines.append("")
    return "\n".join(lines)
