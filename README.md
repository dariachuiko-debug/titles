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
TMDB_API_KEY=...     # опционально, см. "ТТ на изображение"
FANART_API_KEY=...   # опционально, см. "ТТ на изображение"
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
poster = fetch_poster(metadata)  # poster.path, poster.is_original_art, poster.title_is_official

# или всё вместе
metadata, poster = run_pipeline("Guardians of the Galaxy Vol. 2", year=2017)
```

Для масштабирования на список тайтлов достаточно вызывать `run_pipeline` (или
`get_metadata` + `generate_art`) в цикле по списку `(title, year)`.

## ТТ на изображение

- Разрешение: 1280×768 (по умолчанию; переопределяется через `--width`/`--height`
  или параметр `size` у `fetch_poster`/`run_pipeline`)
- Формат: JPEG или PNG (`--image-format`, по умолчанию `jpeg`)

`fetch_poster()` не рисует название сама, если может найти реальный постер,
где название уже есть. Раньше мы просто доверяли источнику "это Kinopoisk,
там наверняка есть текст" — на практике это оказалось не так: и постер с
Kinopoisk, и постер с fanart.tv для одного и того же фильма пришли
полностью без текста (чистый key art). Поэтому сейчас используется другой
подход:

1. **Собираем несколько кандидатов** из всех источников сразу, в приоритете
   русскоязычные: галерея постеров Kinopoisk (не одно поле `poster.url` из
   карточки фильма, а именно галерея — у Kinopoisk на один фильм обычно
   несколько постеров, и у карточки может оказаться textless-вариант, а у
   галереи — с текстом), TMDb (`language=ru`, если задан `TMDB_API_KEY`),
   fanart.tv (`lang=ru`, если задан `FANART_API_KEY`), затем те же
   источники на английском.
2. **Проверяем каждого кандидата локальным OCR** (Tesseract, бесплатно, без
   ключей и без сети) — есть ли на картинке реально читаемый текст. Первый
   кандидат с уверенно распознанным текстом используется **как есть**, без
   перерисовки — это и есть настоящее название настоящим шрифтом студии.
   При обрезке под нужный размер холст смещается вниз (там обычно и
   находится название на постере), чтобы его не обрезало кадрированием.
3. **Если текста не нашлось нигде** — берём кандидата с самым высоким
   исходным разрешением и на нём уже накладываем своё: перевод оригинального
   названия (бесплатный MyMemory API, без ключа), фиксированный шрифт
   (`covergen/assets/fonts/DejaVuSans-Bold.ttf`, кириллица), акцентный цвет,
   подобранный из самой этой картинки. Честно говоря — это подгонка, а не
   воспроизведение фирменного шрифта/цвета студии: точно распознать и
   переиспользовать именно оригинальный шрифт с картинки программно не
   выйдет.
4. **Реального постера не нашлось нигде** — последний фолбэк: Fal.ai рисует
   приближённый арт (реальные кадры фильма ИИ в принципе использовать не
   может — у text-to-image моделей нет доступа к футажу), с тем же
   наложением названия. Это никогда не выдаётся за настоящее: у результата
   `PosterResult.is_original_art=False`.

`PosterResult` явно фиксирует, что получилось на выходе:
- `is_original_art` — реальная ли это художественная часть (True для
  вариантов 1–3, False только для AI-заглушки)
- `title_is_official` — подтверждён ли видимый текст через OCR как родной
  для этой картинки (True для варианта 2, False там, где текст накладывали
  мы сами)

Для OCR нужен установленный `tesseract-ocr` (+ языковой пакет `rus`) —
на GitHub Actions runner ставится через `apt-get` (см. workflow), для
локального запуска: `apt-get install tesseract-ocr tesseract-ocr-rus`
(Debian/Ubuntu) или аналог для вашей ОС.

## Структура

- `covergen/metadata.py` — `get_metadata()`: Kinopoisk (kinopoisk.dev) → OMDb
  fallback; `fetch_kinopoisk_poster_gallery()`: доп. постеры того же фильма
- `covergen/tmdb.py` — `fetch_poster_urls()`: постеры с TMDb, с приоритетом
  языка (опционально, нужен `TMDB_API_KEY`)
- `covergen/fanart.py` — `fetch_poster_urls()`: постеры с fanart.tv по IMDb id,
  с приоритетом языка (опционально, нужен `FANART_API_KEY`)
- `covergen/ocr.py` — `has_visible_text()`: локальная (Tesseract) проверка,
  есть ли на картинке реально читаемый текст
- `covergen/translate.py` — `translate_to_russian()`: бесплатный
  machine-translation фолбэк (MyMemory, без ключа) для случаев без `title_ru`
- `covergen/art.py` — `fetch_poster()`: сбор кандидатов + OCR-проверка (см.
  выше); `generate_art()` — генерация через Fal.ai (`fal-ai/flux/dev`) как
  последний фолбэк
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
variables → Actions): `KINOPOISK_API_KEY`, `OMDB_API_KEY`, `FAL_API_KEY`, и
опционально `TMDB_API_KEY` (https://www.themoviedb.org/settings/api) и/или
`FANART_API_KEY` (Personal API Key в настройках аккаунта на fanart.tv) —
оба нужны только для поиска локализованных постеров; без них пайплайн
просто пропускает соответствующий источник.

Дальше запускать вручную: вкладка Actions → "Generate poster" → Run workflow,
указав `title`/`year`. Результат — артефакт `poster-<run_id>` с файлом из
`output/`.
