# covergen

Генератор обложек к фильмам/сериалам: получает метаданные тайтла (Kinopoisk с
фолбэком на OMDb) и берёт **настоящий официальный постер** (`poster_url` из
метаданных), подгоняя его под нужный размер/формат. Генерация через Fal.ai
(FLUX) используется только как запасной вариант, когда официального постера
вообще нет — и такие обложки — не настоящие кадры/арт, а лишь приближение
ИИ, о чём пайплайн явно предупреждает (`PosterResult.is_original`).

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
from covergen import get_metadata, fetch_poster, run_pipeline

metadata = get_metadata("Guardians of the Galaxy Vol. 2", year=2017)
poster = fetch_poster(metadata)  # poster.path, poster.is_original

# или всё вместе
metadata, poster = run_pipeline("Guardians of the Galaxy Vol. 2", year=2017)
```

Для масштабирования на список тайтлов достаточно вызывать `run_pipeline` (или
`get_metadata` + `generate_art`) в цикле по списку `(title, year)`.

## ТТ на изображение

- Разрешение: 1280×768 (по умолчанию; переопределяется через `--width`/`--height`
  или параметр `size` у `fetch_poster`/`run_pipeline`)
- Формат: JPEG или PNG (`--image-format`, по умолчанию `jpeg`)
- Источник — **настоящий официальный постер** (`metadata.poster_url`),
  обрезанный/масштабированный под нужный размер без перерисовки. Раз это
  реальный постер, название на нём уже набрано официальным шрифтом и цветом
  студии/дистрибьютора — поверх ничего не рисуем.
- Только если официального постера нет вообще — Fal.ai генерирует
  приближённый арт (никакие реальные кадры фильма ИИ использовать не может,
  это принципиальное ограничение text-to-image моделей), и на нём уже
  накладывается название нашим фиксированным шрифтом
  (`covergen/assets/fonts/DejaVuSans-Bold.ttf`, кириллица) — это осознанно
  приближённый, а не официальный вид, и `PosterResult.is_original=False`
  явно это помечает.

Известные ограничения:
- Если Kinopoisk недоступен и метаданные только из OMDb (там нет `title_ru`),
  при AI-фолбэке на обложку ляжет оригинальное (английское) название —
  автоматического перевода нет.
- Если найденный официальный постер без перевода (например, только
  англоязычный) — используется как есть; текст поверх реального постера не
  дорисовываем и шрифт/цвет "на глаз" не подбираем, так как надёжного
  способа программно распознать и воспроизвести шрифт/цвет конкретного
  постера нет.

## Структура

- `covergen/metadata.py` — `get_metadata()`: Kinopoisk (kinopoisk.dev) → OMDb fallback
- `covergen/art.py` — `fetch_poster()`: скачивает и подгоняет реальный
  постер под размер; `generate_art()` — запасной путь через Fal.ai
  (`fal-ai/flux/dev`) с наложением названия, если официального постера нет
- `covergen/pipeline.py` — `run_pipeline()`: метаданные + постер для одного тайтла
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
