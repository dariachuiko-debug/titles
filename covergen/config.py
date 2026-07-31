import os

from dotenv import load_dotenv

load_dotenv()


def get_kinopoisk_api_key() -> str | None:
    return os.getenv("KINOPOISK_API_KEY")


def get_omdb_api_key() -> str | None:
    return os.getenv("OMDB_API_KEY")


def get_fal_api_key() -> str | None:
    return os.getenv("FAL_API_KEY")
