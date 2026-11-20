[![Stand With Ukraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/banner2-direct.svg)](https://vshymanskyy.github.io/StandWithUkraine)
=========

# AutoSample

[![CI](https://github.com/deigineor/AutoSample/actions/workflows/ci.yml/badge.svg)](https://github.com/deigineor/AutoSample/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/deigineor/AutoSample)](https://github.com/deigineor/AutoSample/releases/latest)

Автоматичне семплування хардварних синтезаторів: програма грає ноти по MIDI, записує вихід синта через звукову карту, обробляє і зберігає готовий інструмент.

## Завантаження
Готові збірки — на сторінці [Releases](https://github.com/deigineor/AutoSample/releases/latest):
- **Windows** — `AutoSample-<версія>-windows-x64.exe`, просто запусти.
- **Linux** — `AutoSample-<версія>-linux-x86_64.AppImage`: `chmod +x AutoSample-*.AppImage`, потім запусти. Працює на будь-якому дистрибутиві; потрібен звуковий сервер (ALSA, JACK або PulseAudio/PipeWire).

Контрольні суми — у файлі `SHA256SUMS` біля збірок.

## Запуск із джерел
Подвійний клік по `AutoSample.bat` (при першому запуску сам створить `.venv` і поставить залежності).
Або: `.venv\Scripts\python.exe main.py`

## Як користуватись
1. **Підключення** — драйвер (WASAPI / ASIO), вхід звукової карти, MIDI-порт і канал. Натисни **Тест-нота** — індикатор має ожити.
2. **Виміряти шум** — 1,5 с тиші, програма сама підбере пороги обрізки.
3. **Запис** — діапазон нот і крок, шари velocity, round robin, тривалість ноти та хвоста.
4. **●  Почати запис** — і йди пити каву ☕

## Можливості
- Діапазон нот із кроком, до 16 шарів velocity, до 16 round robin
- Хвіст фіксованої довжини або «до тиші» (автовизначення кінця release)
- Шари експресії: aftertouch (Channel Pressure) або MIDI CC — окремий вимір, як velocity; кросфейди прописуються в SFZ/DecentSampler
- Свел-артикуляція: рампа aftertouch/CC під час ноти, зберігається окремим інструментом «… Swell»
- Визначення реальної висоти тону, попередження про транспонування синта, root note за реальною висотою
- Моніторинг входу й прослуховування через той самий пристрій (працює з ASIO)
- Пакетний запис кількох програм (Program Change + Bank MSB/LSB) — кожна стає окремим інструментом
- Авто-обрізка тиші на початку й у кінці, fade in/out, прибирання DC
- Нормалізація: кожного семпла окремо або всього інструмента (динаміка між шарами зберігається)
- Авто-пошук точок лупу з кросфейдом
- WAV 16/24/32f з root note і лупом у smpl-чанку
- Експорт мапінгу у **SFZ** та **DecentSampler**
- Live-хвиля під час запису, індикатор рівня з кліпом, клавіатура (клік = нота на синт)
- Прослуховування, перезапис і видалення окремих семплів
- Пресети налаштувань; останнє налаштування зберігається автоматично

Гарячі клавіші: **Пробіл** — слухати семпл, **Esc** — стоп.

## Розробка
```
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # Windows: .venv\Scripts\pip
.venv/bin/pytest -q
.venv/bin/ruff check .
```
Локальна збірка: `bash packaging/build_linux.sh` (AppImage) або `bash packaging/build_windows.sh` (exe) — результат у `dist/`. Конфіг PyInstaller — `packaging/autosample.spec`.

## Реліз
1. Підняти `__version__` в `autosample/__init__.py` (semver, наприклад `1.1.0`).
2. Закомітити, створити тег `v1.1.0` (має збігатися з `__version__`) і запушити його: `git tag v1.1.0 && git push origin v1.1.0`.
3. CI збере Windows і Linux, створить GitHub Release з автоматичними нотатками, файлами збірок і `SHA256SUMS`.
