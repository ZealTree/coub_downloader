# Coub Downloader

![Иконка Coub Downloader](assets/icon.png)

Приложение для Windows и Linux: скачивает видео и аудио Coub, объединяет их
в MP4 и при необходимости повторяет видео до конца аудиодорожки.
Поддерживает высокое и среднее качество.

![Интерфейс приложения](docs/interface.png)

## Готовое приложение

Скачайте файл для своей платформы из [GitHub Releases](https://github.com/ZealTree/coub_downloader/releases):

- Windows x64: `CoubDownloader-X.Y.Z-windows-x64.exe`.
- Linux x86_64: `CoubDownloader-X.Y.Z-linux-x86_64`.

Внутри находятся Python, Qt, FFmpeg и ffprobe. Отдельно устанавливать их не нужно.
Windows-сборка предназначена для Windows 10/11 x64. Linux-сборка CI создаётся
на Ubuntu 22.04 и требует glibc 2.35+ и библиотеки графической сессии Qt.
На Linux перед первым запуском выдайте файлу право выполнения:

```sh
chmod +x CoubDownloader-*-linux-x86_64
./CoubDownloader-X.Y.Z-linux-x86_64
```

Подставьте версию скачанного файла вместо `X.Y.Z`.
Сборки каждого push доступны в [GitHub Actions](https://github.com/ZealTree/coub_downloader/actions).
Релиз появляется при отправке соответствующего тега версии.

## Использование

1. Вставьте ссылку `https://coub.com/view/ID` или ID ролика.
2. Выберите папку и имя итогового MP4.
3. Выберите качество и включите зацикливание, если нужно сохранить всю аудиодорожку.
4. Нажмите «Скачать Coub» и дождитесь сообщения о завершении.

По умолчанию используется системная папка загрузок: Windows Known Folders
или Linux XDG; при отсутствии настройки — `~/Downloads`.
Без зацикливания длина ограничивается более короткой дорожкой.
При успешной загрузке существующий файл с тем же именем заменяется.
При ошибке загрузки или обработки прежний файл сохраняется.
Окно нельзя закрыть, пока работает загрузка.

## Запуск из исходников

Для приложения нужны Python 3.10+, PyQt6, requests и FFmpeg/ffprobe в PATH.
Команды выполняются из корня репозитория.

Windows, PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python coub_downloader_gui.py
```

Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python coub_downloader_gui.py
```

Проверка системных инструментов: `ffmpeg -version` и `ffprobe -version`.
Пакет `ffmpeg-python` в зависимостях не устанавливает эти программы;
приложение вызывает их непосредственно.
На Linux необходима графическая сессия и системные библиотеки Qt.

## Сборка

GitHub Actions проверяет версию, собирает нативные Windows/Linux-бинарники
и проверяет запуск готового приложения со встроенными FFmpeg/ffprobe.
Обычные push и pull request создают artifacts; релиз публикуется только по тегу.

[Руководство пользователя и устранение ошибок](docs/README.md) ·
[Сборка и публикация](docs/RELEASING.md)

## Иконки и лицензия

Иконки находятся в `assets/icon.png` и `assets/icon.ico`.
Они используются в интерфейсе и автономной сборке.
В репозитории нет лицензии на код приложения: её должен выбрать владелец.
Условия сторонних компонентов определяются их лицензиями;
сборка включает предоставленную лицензию FFmpeg.
