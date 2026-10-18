import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str
    SORSA_API_KEYS: list[str]
    SORSA_API_BASE_URL: str
    ASSIGNMENT_COUNT: int
    DATABASE_PATH: str
    ADMIN_IDS: list[int]

    @classmethod
    def load(cls) -> "Config":
        bot_token = os.getenv("BOT_TOKEN", "").strip()

        # Parse bulk keys from SORSA_API_KEYS or fallback to SORSA_API_KEY
        raw_keys = os.getenv("SORSA_API_KEYS", "") or os.getenv("SORSA_API_KEY", "")
        # Split by comma, semicolon, newline, or whitespace
        sorsa_api_keys = [
            k.strip()
            for k in re.split(r"[\r\n,;\s]+", raw_keys)
            if k.strip() and not k.strip().startswith("#")
        ]

        sorsa_api_base_url = os.getenv("SORSA_API_BASE_URL", "https://api.sorsa.io/v3").rstrip("/")

        try:
            assignment_count = int(os.getenv("ASSIGNMENT_COUNT", "15"))
        except ValueError:
            assignment_count = 15

        database_path = os.getenv("DATABASE_PATH", "engagement_bot.db").strip()

        admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
        admin_ids = []
        if admin_ids_raw:
            for item in re.split(r"[\r\n,;\s]+", admin_ids_raw):
                cleaned = item.strip()
                if cleaned.isdigit():
                    admin_ids.append(int(cleaned))

        return cls(
            BOT_TOKEN=bot_token,
            SORSA_API_KEYS=sorsa_api_keys,
            SORSA_API_BASE_URL=sorsa_api_base_url,
            ASSIGNMENT_COUNT=assignment_count,
            DATABASE_PATH=database_path,
            ADMIN_IDS=admin_ids,
        )


config = Config.load()
