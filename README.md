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
```

Запускает пайплайн на тестовом тайтле "Guardians of the Galaxy Vol. 2" (2017):
получает метаданные и сохраняет сгенерированную обложку в `output/`.

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

## Структура

- `covergen/metadata.py` — `get_metadata()`: Kinopoisk (kinopoisk.dev) → OMDb fallback
- `covergen/art.py` — `generate_art()`: сборка промпта и генерация через Fal.ai (`fal-ai/flux/dev`)
- `covergen/pipeline.py` — `run_pipeline()`: метаданные + арт для одного тайтла
- `main.py` — тестовый прогон пайплайна на одном тайтле
- `tests/` — офлайн-тесты парсинга метаданных и сборки промпта (без сетевых вызовов)

## Тесты

```bash
python3 -m unittest discover -s tests
```
