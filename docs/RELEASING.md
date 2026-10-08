# Сборка и релизы

[Главная страница](../README.md)

## Версия и GitHub CI

`version.txt` — единственный источник версии `MAJOR.MINOR.PATCH` без ведущих
нулей. Тег должен быть ровно `v` плюс эта версия; несовпадение останавливает CI.
Версия не повышается автоматически.

`.github/workflows/release.yml` запускается для push любой ветки, pull request,
тегов `v*.*.*` и вручную. Нативные runners: `windows-2022` и `ubuntu-22.04`,
Python 3.12. CI проверяет версию, устанавливает закреплённые зависимости,
загружает FFmpeg с проверкой SHA256, собирает PyInstaller `--onefile`
и запускает `ci/smoke.py` для проверки готового бинарника.

Готовая сборка содержит Python, Qt, FFmpeg/ffprobe, версию, иконки и лицензию
FFmpeg. Проверка сборки проверяет ресурсы, запуск окна и встроенных инструментов,
а также обработку синтетических дорожек в обоих режимах. На Linux используется
`xvfb-run`, на Windows — Qt `offscreen`. Отдельного набора тестов в этой публичной
копии нет.

Выходные файлы:

- `CoubDownloader-X.Y.Z-windows-x64.exe` — Windows 10/11 x64.
- `CoubDownloader-X.Y.Z-linux-x86_64` — Linux, glibc 2.35+ и библиотеки Qt.

Push в ветку, PR и ручной запуск не публикуют релиз. Push тега после обеих
успешных сборок прикрепляет два исполняемых файла непосредственно к GitHub
Release. ZIP используется только как контейнер Actions artifacts.

## Локальная сборка

Используйте отдельное окружение Python 3.12+ и команды из корня репозитория:

```sh
python -m pip install -r requirements-build.txt
python ci/version.py
python ci/download_ffmpeg.py
python build_windows.py --ffmpeg-dir build/ffmpeg-download/ffmpeg
python ci/smoke.py
```

Системные графические зависимости Linux перечислены в workflow.
`requirements-build.txt` подключает закреплённый `ci/requirements.txt`.
Историческое имя `build_windows.py` сохранено: скрипт собирает Windows/Linux x64
на соответствующей платформе. Можно передать собственную папку с настоящими
FFmpeg/ffprobe и `LICENSE` или `LICENSE.txt`; ярлыки пакетного менеджера не подходят.
Результат — в `dist`, временные файлы и `smoke.json` — в `build`.

## Выпуск версии

После проверки изменений увеличьте версию и создайте коммит:

```sh
python bump_version.py --part patch
python ci/version.py
git add version.txt
git commit -m "chore: bump release version"
git push origin main
```

Дождитесь успешного CI, затем создайте тег с версией из `version.txt`:

```sh
git tag vX.Y.Z
git push origin vX.Y.Z
```

Замените `X.Y.Z` реальной версией. Для minor/major используйте `--part minor`
или `--part major`. Выпущенные теги не передвигайте. При переносе исходников
из основного проекта сохраняйте публичный состав файлов и Git-историю зеркала.

Публикация выполняется `ci/publish_github.py` через CLI `gh` и временный
`github.token`. Право `contents: write` выдаётся только release job.
Проверяются версия, checkout и коммит тега. Сначала создаётся draft,
затем загружаются оба бинарника и проверяются их размеры, после чего релиз
публикуется. При сбое черновик можно дозаполнить повторным запуском;
опубликованные релизы не перезаписываются.
