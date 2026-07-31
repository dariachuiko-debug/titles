# covergen

Генератор обложек к фильмам/сериалам: получает метаданные тайтла (Kinopoisk с
фолбэком на OMDb) и генерирует постер через Fal.ai (FLUX).

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # и заполнить ключи
```

`.env`:

```
KINOPOISK_API_KEY=...
OMDB_API_KEY=...
FAL_API_KEY=...
```

## Использование

```bash
python3 main.py
python3 main.py --title "Дюна" --year 2021
python3 main.py --kinopoisk-id 462
```

Без аргументов запускает пайплайн на тестовом тайтле "Guardians of the Galaxy
Vol. 2" (2017): получает метаданные и сохраняет сгенерированную обложку в
`output/`.

Программный интерфейс:

```python
from covergen import get_metadata, generate_art, run_pipeline

metadata = get_metadata("Guardians of the Galaxy Vol. 2", year=2017)
image_path = generate_art(metadata)

# или всё вместе
metadata, image_path = run_pipeline("Guardians of the Galaxy Vol. 2", year=2017)
```

Для масштабирования на список тайтлов достаточно вызывать `run_pipeline` (или
`get_metadata` + `generate_art`) в цикле по списку `(title, year)`.

## ТТ на изображение

- Разрешение: 1280×768 (по умолчанию; переопределяется через `--width`/`--height`
  или параметр `size` у `generate_art`/`run_pipeline`)
- Формат: JPEG или PNG (`--image-format`, по умолчанию `jpeg`)
- На постер накладывается название **на русском** (`title_ru` из Kinopoisk,
  если есть; иначе — `title_original`) одним фиксированным шрифтом
  (`covergen/assets/fonts/DejaVuSans-Bold.ttf`, с поддержкой кириллицы),
  чтобы шрифт был одинаковым на любой машине, где бы ни запускался пайплайн.
  Сам Fal.ai просят не рисовать текст в самом изображении — заголовок кладём
  поверх средствами Pillow.

Известное ограничение: если Kinopoisk недоступен и метаданные приходят только
из OMDb (там нет русского названия), на постере ляжет оригинальное
(английское) название — автоматического перевода пока нет. Если понадобится
переводить и такие случаи — нужно подключать отдельный translation API.

## Структура

- `covergen/metadata.py` — `get_metadata()`: Kinopoisk (kinopoisk.dev) → OMDb fallback
- `covergen/art.py` — `generate_art()`: промпт + генерация через Fal.ai (`fal-ai/flux/dev`),
  затем подгонка под целевой размер и наложение русского названия
- `covergen/pipeline.py` — `run_pipeline()`: метаданные + арт для одного тайтла
- `main.py` — тестовый прогон пайплайна на одном тайтле
- `tests/` — офлайн-тесты парсинга метаданных, сборки промпта и рендера обложки
  (без сетевых вызовов)

## Тесты

```bash
python3 -m unittest discover -s tests
```

## Запуск через GitHub Actions

Kinopoisk, OMDb и Fal.ai могут быть недоступны из некоторых песочниц/CI со
строгой сетевой политикой. `.github/workflows/generate-poster.yml` запускает
пайплайн на раннере GitHub (у него открытый доступ в интернет) и кладёт
сгенерированную обложку в артефакт запуска.

Перед первым запуском добавьте секреты репозитория (Settings → Secrets and
variables → Actions): `KINOPOISK_API_KEY`, `OMDB_API_KEY`, `FAL_API_KEY`.

Дальше запускать вручную: вкладка Actions → "Generate poster" → Run workflow,
указав `title`/`year`. Результат — артефакт `poster-<run_id>` с файлом из
`output/`.
