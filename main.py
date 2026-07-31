import logging

from covergen.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

TEST_TITLE = "Guardians of the Galaxy Vol. 2"
TEST_YEAR = 2017


def main() -> None:
    metadata, image_path = run_pipeline(TEST_TITLE, year=TEST_YEAR)

    print("=== Metadata ===")
    print(f"source:          {metadata.source}")
    print(f"title_ru:        {metadata.title_ru}")
    print(f"title_original:  {metadata.title_original}")
    print(f"year:            {metadata.year}")
    print(f"genres:          {', '.join(metadata.genres)}")
    print(f"poster_url:      {metadata.poster_url}")
    print(f"description:     {metadata.description}")
    print()
    print("=== Generated art ===")
    print(f"saved to:        {image_path}")


if __name__ == "__main__":
    main()
