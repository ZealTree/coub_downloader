import sys
import os
import subprocess
import json
import re
import time
import tempfile
import math
from urllib.parse import urlparse

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar,
                             QFileDialog, QTextEdit, QStatusBar, QComboBox, QMessageBox)
from PyQt6.QtCore import QThread, pyqtSignal, QStandardPaths
from PyQt6.QtGui import QIcon

import requests
from media_tools import find_media_tools, find_working_tool, windows_process_options
from app_paths import default_download_dir, resource_path

def media_executable(name):
    """Prefer the bundled executable in a frozen Windows distribution."""
    return find_working_tool(name)


def subprocess_options():
    return windows_process_options()


def probe_media(file_path, executable=None):
    executable = executable or media_executable("ffprobe")
    if not executable:
        raise OSError("ffprobe not found")
    result = subprocess.run(
        [executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", file_path],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        check=True, **subprocess_options(),
    )
    return json.loads(result.stdout)


def get_default_download_directory():
    """Use Windows Known Folders / Linux XDG user directories through Qt."""
    directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return directory or str(default_download_dir())


# Расширенные заголовки: Referer и Origin критически важны для CDN Coub
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://coub.com/',
    'Origin': 'https://coub.com',
    'Sec-Fetch-Dest': 'video',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'Connection': 'keep-alive'
}

# Сессия для повторного использования соединений
http_session = requests.Session()

def reset_session():
    """Пересоздает сессию, если CDN сбросил соединение."""
    global http_session
    http_session.close()
    http_session = requests.Session()

def create_download_directory(directory):
    try:
        os.makedirs(directory, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b"test")
            probe.flush()
        return True
    except Exception as e:
        print(f"Ошибка при создании/проверке директории: {e}")
        return False

def check_ffmpeg():
    return find_media_tools() is not None


def parse_coub_id(value):
    value = value.strip()
    if re.fullmatch(r"[a-zA-Z0-9]+", value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("coub.com", "www.coub.com"):
        raise ValueError("Введите ссылку https://coub.com/view/ID или ID Coub")
    match = re.fullmatch(r"/view/([a-zA-Z0-9]+)/?", parsed.path)
    if not match:
        raise ValueError("Не удалось распознать ID Coub")
    return match.group(1)


def get_media_urls(coub_url, quality="high"):
    try:
        # Пауза 1 сек перед обращением к API, чтобы снизить частые запросы
        time.sleep(1)

        coub_id = parse_coub_id(coub_url)

        api_url = f"https://coub.com/api/v2/coubs/{coub_id}"
        response = http_session.get(api_url, headers=BROWSER_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        video_versions = data.get('file_versions', {}).get('html5', {})
        video_quality = "med" if quality.lower() in ("medium", "med") else quality.lower()
        video_url = video_versions.get('video', {}).get(video_quality, {}).get('url')
        audio_url = video_versions.get('audio', {}).get(video_quality, {}).get('url')

        if not video_url or not audio_url:
            raise ValueError("Не удалось найти ссылки на видео или аудио в ответе API")

        return video_url, audio_url
    except Exception as e:
        print(f"Ошибка получения медиа-URL: {e}")
        reset_session()
        return None, None

def download_file(url, filepath):
    try:
        # Небольшая задержка перед загрузкой каждого потока
        time.sleep(0.5)

        # Важно: контекстный менеджер `with` автоматически закрывает соединение при выходе
        with http_session.get(url, stream=True, headers=BROWSER_HEADERS, timeout=15) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress = min(100, int((downloaded / total_size) * 100)) if total_size > 0 else 0
                        yield progress
        if downloaded == 0:
            raise ValueError("Сервер вернул пустой медиафайл")
        if total_size and not response.headers.get('content-encoding') and downloaded != total_size:
            raise ValueError("Медиафайл скачан не полностью")
        yield 100
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
        reset_session()  # При ошибке полностью очищаем сокеты
        yield -1

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)

    def __init__(self, coub_url, filename, loop, quality, download_dir,
                 ffmpeg_path=None, ffprobe_path=None):
        super().__init__()
        self.coub_url = coub_url
        self.filename = filename
        self.loop = loop
        self.quality = quality
        self.download_dir = download_dir
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def run_ffmpeg_subprocess(self, cmd, task_name, start_progress, progress_weight, total_duration):
        self.update_signal.emit(f"Запуск: {task_name}...")
        full_cmd = [self.ffmpeg_path or media_executable('ffmpeg'), '-nostdin', '-progress', 'pipe:1', '-nostats'] + cmd
        process = subprocess.Popen(
            full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1, **subprocess_options()
        )

        for line in process.stdout:
            if "out_time=" in line and total_duration:
                try:
                    time_str = line.split("out_time=")[-1].split()[0]
                    h, m, s = time_str.split(':')
                    seconds = int(h) * 3600 + int(m) * 60 + float(s)
                    stage_p = max(0.0, min(seconds / total_duration, 1.0))
                    actual_p = min(99, int(start_progress + (stage_p * progress_weight)))
                    self.progress_signal.emit(actual_p)
                except:
                    pass
            elif "Error" in line or "failed" in line or "Invalid" in line:
                self.update_signal.emit(f"FFmpeg: {line.strip()}")

        process.stdout.close()
        process.wait()
        return process.returncode == 0

    def run(self):
        success = False
        try:
            # The directory belongs exclusively to this job; never clean up by filename.
            with tempfile.TemporaryDirectory(prefix="coub-", dir=self.download_dir) as work_dir:
                success = self.download_and_merge(work_dir)
        except Exception as e:
            self.update_signal.emit(f"Критическая ошибка в потоке: {e}")
        if success:
            self.progress_signal.emit(100)
        self.finished_signal.emit(success)

    def download_and_merge(self, work_dir):
        temp_video = os.path.join(work_dir, "video.mp4")
        temp_audio = os.path.join(work_dir, "audio")
        temp_output = os.path.join(work_dir, "output.mp4")
        final_path = os.path.join(self.download_dir, self.filename)
        video_url, audio_url = get_media_urls(self.coub_url, self.quality)
        if not video_url or not audio_url:
            self.update_signal.emit("Не удалось получить ссылки на медиа")
            return False

        for url, path, label, offset in (
            (video_url, temp_video, "видео", 0),
            (audio_url, temp_audio, "аудио", 40),
        ):
            self.update_signal.emit(f"Скачивание {label}-потока...")
            for progress in download_file(url, path):
                if progress == -1:
                    return False
                self.progress_signal.emit(int(offset + progress * 0.4))

        audio_duration = self.get_media_duration(temp_audio, "audio")
        video_duration = self.get_media_duration(temp_video, "video")
        duration = audio_duration if self.loop else (
            min(audio_duration, video_duration) if audio_duration and video_duration else None
        )
        cmd = ['-y']
        if self.loop:
            cmd += ['-stream_loop', '-1']
        cmd += ['-i', temp_video, '-i', temp_audio,
                '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0']
        if duration:
            cmd += ['-t', str(duration)]
        cmd += ['-shortest', temp_output]
        if not self.run_ffmpeg_subprocess(cmd, "Сборка медиафайла", 80, 20, duration):
            return False
        # Replace only after successful processing; failed jobs preserve the old output.
        os.replace(temp_output, final_path)
        return True

    def get_media_duration(self, file_path, codec_type):
        try:
            probe = probe_media(file_path, self.ffprobe_path)
            for stream in probe.get('streams', []):
                if stream.get('codec_type') == codec_type:
                    try:
                        duration = float(stream.get('duration', 0))
                        if math.isfinite(duration) and duration > 0:
                            return duration
                    except (ValueError, TypeError):
                        pass
            duration = float(probe.get('format', {}).get('duration', 0))
            return duration if math.isfinite(duration) and duration > 0 else None
        except (subprocess.SubprocessError, OSError, ValueError, TypeError):
            return None

class CoubDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Загрузчик Coub")
        self.setGeometry(100, 100, 720, 500)
        icon_name = "assets/icon.ico" if os.name == "nt" else "assets/icon.png"
        icon = QIcon(str(resource_path(icon_name)))
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        self.download_dir = get_default_download_directory()
        self.download_thread = None
        self.init_ui()
        self.apply_modern_theme()
        if not create_download_directory(self.download_dir):
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать директорию: {self.download_dir}")

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        url_layout = QHBoxLayout()
        url_label = QLabel("URL Coub:")
        url_label.setFixedWidth(110)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://coub.com/view/...")
        self.url_input.textChanged.connect(self.update_filename_from_url)
        paste_btn = QPushButton("Вставить")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(paste_btn)

        file_layout = QHBoxLayout()
        file_label = QLabel("Имя файла:")
        file_label.setFixedWidth(110)
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("output.mp4")
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_directory)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Высокое качество", "Среднее качество"])
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(browse_btn)
        file_layout.addWidget(self.quality_combo)

        dir_layout = QHBoxLayout()
        dir_label = QLabel("Папка сохранения:")
        dir_label.setFixedWidth(110)
        self.dir_input = QLineEdit()
        self.dir_input.setText(self.download_dir)
        dir_browse_btn = QPushButton("Выбрать...")
        dir_browse_btn.clicked.connect(self.browse_download_dir)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(dir_browse_btn)

        self.loop_checkbox = QCheckBox("Зациклить видео под длину аудиодорожки")
        self.loop_checkbox.setChecked(True)

        self.download_btn = QPushButton("Скачать Coub")
        self.download_btn.setObjectName("download_btn")
        self.download_btn.clicked.connect(self.start_download)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Лог выполнения процесса...")

        layout.addLayout(url_layout)
        layout.addLayout(file_layout)
        layout.addLayout(dir_layout)
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(self.download_btn)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_output)

        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Система готова к работе")

        clipboard_text = QApplication.clipboard().text().strip()
        if "coub.com" in clipboard_text:
            self.url_input.setText(clipboard_text)

        paste_btn.clicked.connect(self.paste_from_clipboard)

    def apply_modern_theme(self):
        dark_stylesheet = """
            QMainWindow {
                background-color: #121214;
            }
            QLabel {
                color: #e0e0e6;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #1a1a1e;
                border: 1px solid #2d2d34;
                border-radius: 5px;
                color: #ffffff;
                padding: 4px 8px;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #5c6bc0;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox::down-arrow {
                image: url("__CHEVRON_ICON__");
                width: 12px;
                height: 12px;
            }
            QPushButton {
                background-color: #2d2d34;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 500;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
            }
            QPushButton:pressed {
                background-color: #1a1a1e;
            }
            QPushButton#download_btn {
                background-color: #5c6bc0;
                color: #ffffff;
                padding: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#download_btn:hover {
                background-color: #4f5bba;
            }
            QPushButton#download_btn:disabled {
                background-color: #202024;
                color: #55555c;
            }
            QCheckBox {
                color: #e0e0e6;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #2d2d34;
                background-color: #1a1a1e;
            }
            QCheckBox::indicator:checked {
                image: url("__CHECK_ICON__");
                background-color: #5c6bc0;
                border: 1px solid #5c6bc0;
            }
            QProgressBar {
                border: 1px solid #2d2d34;
                border-radius: 5px;
                text-align: center;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                background-color: #1a1a1e;
                height: 16px;
            }
            QProgressBar::chunk {
                background-color: #5c6bc0;
                border-radius: 4px;
            }
            QStatusBar {
                color: #8a8a93;
                background-color: #1a1a1e;
                border-top: 1px solid #2d2d34;
            }

            QMessageBox {
                background-color: #1a1a1e;
            }
            QMessageBox QLabel {
                color: #ffffff;
                font-size: 12px;
                background-color: transparent;
            }
            QMessageBox QPushButton {
                background-color: #2d2d34;
                color: #ffffff;
                border: 1px solid #3e3e4a;
                min-width: 65px;
                padding: 4px;
            }
            QMessageBox QPushButton:hover {
                background-color: #3e3e4a;
            }
        """
        dark_stylesheet = dark_stylesheet.replace("__CHECK_ICON__", resource_path("assets/checkmark.svg").as_posix())
        dark_stylesheet = dark_stylesheet.replace("__CHEVRON_ICON__", resource_path("assets/chevron-down.svg").as_posix())
        self.setStyleSheet(dark_stylesheet)

    def browse_directory(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить видео Coub", self.dir_input.text().strip(), "MP4 файлы (*.mp4)")
        if filename:
            self.download_dir = os.path.dirname(filename)
            self.dir_input.setText(self.download_dir)
            self.file_input.setText(os.path.basename(filename))

    def browse_download_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Выберите папку для загрузки", self.download_dir)
        if dir_path:
            self.download_dir = dir_path
            self.dir_input.setText(dir_path)

    def paste_from_clipboard(self):
        self.url_input.setText(QApplication.clipboard().text())

    def update_filename_from_url(self):
        url = self.url_input.text().strip()
        match = re.search(r'view/([a-zA-Z0-9]+)', url)
        if match:
            self.file_input.setText(f"coub_{match.group(1)}.mp4")

    def start_download(self):
        if self.download_thread is not None:
            return
        media_tools = find_media_tools()
        if media_tools is None:
            QMessageBox.critical(self, "Ошибка", "Не удалось запустить FFmpeg/ffprobe: проверьте комплектные файлы приложения или установку FFmpeg в PATH.")
            return

        coub_url = self.url_input.text().strip()
        filename = self.file_input.text().strip()
        loop = self.loop_checkbox.isChecked()
        quality = "high" if "Высокое" in self.quality_combo.currentText() else "medium"
        self.download_dir = self.dir_input.text().strip()

        if not coub_url:
            QMessageBox.warning(self, "Ошибка", "Введите URL Coub")
            return

        try:
            coub_id = parse_coub_id(coub_url)
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка", str(error))
            return
        if not filename:
            filename = f"coub_{coub_id}.mp4"

        if os.path.basename(filename) != filename or any(c in filename for c in '/\\'):
            QMessageBox.warning(self, "Ошибка", "Введите только имя файла, а папку укажите отдельно.")
            return
        if os.name == "nt" and (
            any(c in filename for c in '<>:"|?*')
            or any(ord(c) < 32 for c in filename)
            or filename.endswith((".", " "))
            or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", filename, re.IGNORECASE)
        ):
            QMessageBox.warning(self, "Ошибка", "Недопустимое имя файла Windows.")
            return
        if not filename.lower().endswith(".mp4"):
            filename += ".mp4"
        self.file_input.setText(filename)

        if not create_download_directory(self.download_dir):
            QMessageBox.critical(self, "Ошибка", f"Нет прав на запись в папку: {self.download_dir}")
            return

        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.log_output.append(f"Начало загрузки: {coub_url}")

        self.download_thread = DownloadThread(coub_url, filename, loop, quality, self.download_dir, *media_tools)
        self.download_thread.update_signal.connect(self.update_log_and_status)
        self.download_thread.progress_signal.connect(self.progress_bar.setValue)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.finished.connect(self.release_download_thread)
        self.download_thread.start()

    def update_log_and_status(self, message):
        self.log_output.append(message)
        if "Скачивание" in message or "Сборка" in message:
            self.status_bar.showMessage(message)

    def download_finished(self, success):
        self.progress_bar.setVisible(False)
        if success:
            self.status_bar.showMessage("Файл успешно скачан")
            QMessageBox.information(self, "Успех", "Файл успешно сохранен!")
        else:
            self.status_bar.showMessage("Ошибка при скачивании")
            QMessageBox.critical(self, "Ошибка", "Не удалось скачать или обработать файл.")

    def release_download_thread(self):
        if self.download_thread is not None:
            self.download_thread.deleteLater()
            self.download_thread = None
        self.download_btn.setEnabled(True)

    def closeEvent(self, event):
        if self.download_thread is not None and self.download_thread.isRunning():
            QMessageBox.information(self, "Загрузка выполняется", "Дождитесь завершения загрузки.")
            event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CoubDownloaderGUI()
    window.show()
    sys.exit(app.exec())
