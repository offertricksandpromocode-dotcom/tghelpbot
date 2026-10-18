import re
from typing import Optional, Tuple

# Matches x.com and twitter.com links with tweet status ID
# Examples:
# https://x.com/username/status/1234567890123456789
# https://twitter.com/user_name/status/1234567890123456789?s=20
# https://mobile.x.com/i/status/1234567890123456789
TWEET_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:mobile\.)?(?:twitter\.com|x\.com)/(?:#!/)?(?P<username>[A-Za-z0-9_]{1,50})/status/(?P<tweet_id>\d+)(?:\S*)?",
    re.IGNORECASE
)

# Twitter handles: 1-15 characters, alphanumeric and underscores
HANDLE_PATTERN = re.compile(r"^@?([A-Za-z0-9_]{1,25})$")


def extract_tweet_info(text: str) -> Optional[Tuple[str, str, str]]:
    """
    Extracts (canonical_url, tweet_id, username) from a string if it contains an X/Twitter post link.
    Returns None if no valid tweet link is found.
    """
    match = TWEET_URL_PATTERN.search(text.strip())
    if not match:
        return None
    
    username = match.group("username")
    tweet_id = match.group("tweet_id")
    canonical_url = f"https://x.com/{username}/status/{tweet_id}"
    
    return canonical_url, tweet_id, username


def clean_handle(handle: str) -> Optional[str]:
    """
    Cleans and normalizes an X/Twitter handle:
    - Strips leading '@' and whitespace
    - Validates characters
    - Returns lowercase handle or None if invalid
    """
    if not handle:
        return None
    cleaned = handle.strip()
    match = HANDLE_PATTERN.match(cleaned)
    if match:
        return match.group(1).lower()
    return None
