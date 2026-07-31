import argparse
import logging

from covergen.art import CANVAS_SIZE, DEFAULT_IMAGE_FORMAT
from covergen.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

DEFAULT_TITLE = "Guardians of the Galaxy Vol. 2"
DEFAULT_YEAR = 2017


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a poster for a movie/series title")
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--kinopoisk-id", type=int, default=None)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--width", type=int, default=CANVAS_SIZE[0])
    parser.add_argument("--height", type=int, default=CANVAS_SIZE[1])
    parser.add_argument("--image-format", choices=["jpeg", "png"], default=DEFAULT_IMAGE_FORMAT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata, image_path = run_pipeline(
        args.title,
        year=args.year,
        kinopoisk_id=args.kinopoisk_id,
        output_dir=args.output_dir,
        size=(args.width, args.height),
        image_format=args.image_format,
    )

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
