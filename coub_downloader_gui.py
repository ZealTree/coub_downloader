import sys
import os
import json
import shutil
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, 
                            QFileDialog, QTextEdit, QStatusBar, QComboBox, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QProcess
from PyQt5.QtGui import QClipboard, QIcon
import requests
import ffmpeg

# 1. Изменение директории загрузок на кроссплатформенную версию
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "CoubDownloads")

def create_download_directory(directory):
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
        # 5. Проверка прав на запись
        test_file = os.path.join(directory, "test_permission")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception as e:
        print(f"Ошибка при создании/проверке директории: {e}")
        return False

def check_ffmpeg():
    # 7. Более надежная проверка FFmpeg
    try:
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            return False
        
        # Проверяем версию FFmpeg
        process = QProcess()
        process.start("ffmpeg", ["-version"])
        process.waitForFinished(5000)
        if process.exitCode() == 0:
            return True
        return False
    except Exception as e:
        print(f"Ошибка при проверке FFmpeg: {e}")
        return False

def get_media_urls(coub_url, quality="high"):
    try:
        coub_id = coub_url.split('/')[-1]
        api_url = f"https://coub.com/api/v2/coubs/{coub_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        video_versions = data.get('file_versions', {}).get('html5', {})
        video_quality = quality.lower()
        video_url = video_versions.get('video', {}).get(video_quality, {}).get('url')
        audio_url = video_versions.get('audio', {}).get(video_quality, {}).get('url')
        
        if not video_url or not audio_url:
            raise ValueError("Не удалось найти ссылки на видео или аудио в ответе API")
            
        return video_url, audio_url
        
    except requests.RequestException as e:
        print(f"Ошибка запроса к API: {e}")
        return None, None
    except ValueError as e:
        print(f"Ошибка данных: {e}")
        return None, None

def download_file(url, filepath):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress = int((downloaded / total_size) * 100) if total_size > 0 else 0
                    yield progress
        yield 100
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
        yield -1

class FFmpegTask(QThread):
    progress_updated = pyqtSignal(int)
    message_emitted = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, command, task_name=""):
        super().__init__()
        self.command = command
        self.task_name = task_name
        self.process = None

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode('utf-8')
        if "out_time=" in data:
            time_str = data.split("out_time=")[-1].split()[0]
            try:
                h, m, s = time_str.split(':')
                seconds = int(h)*3600 + int(m)*60 + float(s)
                self.progress_updated.emit(int(seconds))
            except:
                pass
        self.message_emitted.emit(data)

    def run(self):
        try:
            self.process = QProcess()
            self.process.readyReadStandardError.connect(self.handle_stderr)
            self.message_emitted.emit(f"Запуск {self.task_name}...")
            self.process.start('ffmpeg', self.command)
            self.process.waitForFinished(-1)
            
            exit_code = self.process.exitCode()
            if exit_code == 0:
                self.message_emitted.emit(f"{self.task_name} успешно завершено")
                self.finished.emit(True)
            else:
                self.message_emitted.emit(f"{self.task_name} завершено с ошибкой, код: {exit_code}")
                self.finished.emit(False)
        except Exception as e:
            self.message_emitted.emit(f"Ошибка: {str(e)}")
            self.finished.emit(False)

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)

    def __init__(self, coub_url, filename, loop, quality, download_dir):
        super().__init__()
        self.coub_url = coub_url
        self.filename = filename
        self.loop = loop
        self.quality = quality
        self.download_dir = download_dir
        self.ffmpeg_tasks = []
        self.current_stage = None

    def run(self):
        try:
            # 2. Использование os.path.join для всех путей
            temp_video = os.path.join(self.download_dir, f"temp_video_{self.filename}")
            temp_audio = os.path.join(self.download_dir, f"temp_audio_{self.filename}")
            looped_video = os.path.join(self.download_dir, f"looped_video_{self.filename}")
            final_path = os.path.join(self.download_dir, self.filename)

            video_url, audio_url = get_media_urls(self.coub_url, self.quality)
            if not video_url or not audio_url:
                self.update_signal.emit("Не удалось получить ссылки на медиа")
                self.finished_signal.emit(False)
                return

            # Этап 1: Скачивание видео (0–40%)
            self.current_stage = "video_download"
            self.update_signal.emit("Скачивание видео...")
            for progress in download_file(video_url, temp_video):
                if progress == -1:
                    self.finished_signal.emit(False)
                    return
                scaled_progress = int(progress * 0.4)
                self.progress_signal.emit(scaled_progress)
            
            # Этап 2: Скачивание аудио (40–80%)
            self.current_stage = "audio_download"
            self.update_signal.emit("Скачивание аудио...")
            for progress in download_file(audio_url, temp_audio):
                if progress == -1:
                    self.finished_signal.emit(False)
                    return
                scaled_progress = int(40 + progress * 0.4)
                self.progress_signal.emit(scaled_progress)

            if self.loop:
                # Этап 3: Зацикливание (80–90%)
                self.current_stage = "looping"
                self.update_signal.emit("Зацикливание видео для соответствия длине аудио...")
                video_duration = self.get_duration(temp_video)
                audio_duration = self.get_duration(temp_audio)
                
                if not video_duration or not audio_duration:
                    self.finished_signal.emit(False)
                    return
                
                if video_duration >= audio_duration:
                    cmd = ['-y', '-i', temp_video, '-c', 'copy', '-t', str(audio_duration), looped_video]
                    task = FFmpegTask(cmd, "Обрезка видео")
                else:
                    loop_count = int(audio_duration // video_duration) + 1
                    cmd = ['-y', '-stream_loop', str(loop_count), '-i', temp_video, '-c:v', 'libx264', '-t', str(audio_duration), looped_video]
                    task = FFmpegTask(cmd, "Зацикливание видео")
                
                task.message_emitted.connect(self.update_signal)
                task.progress_updated.connect(self.handle_looping_progress)
                task.finished.connect(lambda success: self.on_ffmpeg_task_completed(success, "зацикливание"))
                self.ffmpeg_tasks.append(task)
                task.start()
                task.wait()
                
                if not task.process.exitCode() == 0:
                    self.finished_signal.emit(False)
                    return
                
                video_to_merge = looped_video
            else:
                video_to_merge = temp_video
                self.progress_signal.emit(90)

            # Этап 4: Объединение (90–100%)
            self.current_stage = "merging"
            self.update_signal.emit("Объединение видео и аудио...")
            video_duration = self.get_duration(video_to_merge)
            cmd = ['-y', '-i', video_to_merge, '-i', temp_audio, '-c:v', 'libx264', '-c:a', 'aac', '-strict', 'experimental', '-t', str(video_duration), final_path]
            
            task = FFmpegTask(cmd, "Объединение потоков")
            task.message_emitted.connect(self.update_signal)
            task.progress_updated.connect(self.handle_merging_progress)
            task.finished.connect(lambda success: self.on_ffmpeg_task_completed(success, "объединение"))
            self.ffmpeg_tasks.append(task)
            task.start()
            task.wait()
            
            if task.process.exitCode() == 0:
                self.cleanup_temp_files(temp_video, temp_audio, looped_video if self.loop else None)
                self.progress_signal.emit(100)
                self.finished_signal.emit(True)
            else:
                self.finished_signal.emit(False)

        except Exception as e:
            self.update_signal.emit(f"Ошибка: {e}")
            self.cleanup_temp_files(temp_video, temp_audio, looped_video if self.loop else None)
            self.finished_signal.emit(False)

    def handle_looping_progress(self, seconds):
        if self.current_stage == "looping":
            total_duration = self.get_duration(os.path.join(self.download_dir, f"temp_audio_{self.filename}"))
            if total_duration:
                progress = int(80 + (seconds / total_duration) * 10)
                self.progress_signal.emit(min(progress, 90))

    def handle_merging_progress(self, seconds):
        if self.current_stage == "merging":
            total_duration = self.get_duration(os.path.join(self.download_dir, f"temp_video_{self.filename}"))
            if total_duration:
                progress = int(90 + (seconds / total_duration) * 10)
                self.progress_signal.emit(min(progress, 100))

    def get_duration(self, file_path):
        try:
            probe = ffmpeg.probe(file_path)
            duration = float(probe['streams'][0]['duration'])
            return duration
        except Exception as e:
            self.update_signal.emit(f"Ошибка получения длительности: {e}")
            return None

    def on_ffmpeg_task_completed(self, success, task_name):
        if not success:
            self.update_signal.emit(f"Ошибка при {task_name}")
            self.finished_signal.emit(False)

    def cleanup_temp_files(self, *files):
        for file in files:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    self.update_signal.emit(f"Ошибка при удалении временного файла {file}: {e}")

class CoubDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Загрузчик Coub")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon("icon.ico"))
        self.download_dir = DEFAULT_DOWNLOAD_DIR
        self.init_ui()
        if not create_download_directory(self.download_dir):
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать/проверить директорию для загрузок: {self.download_dir}")

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # URL Input
        url_layout = QHBoxLayout()
        url_label = QLabel("URL Coub:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://coub.com/view/...")
        self.url_input.textChanged.connect(self.update_filename_from_url)
        paste_btn = QPushButton("Вставить")
        paste_btn.clicked.connect(self.paste_from_clipboard)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(paste_btn)
        
        # Filename Input and Quality Selection
        file_layout = QHBoxLayout()
        file_label = QLabel("Имя файла:")
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("output.mp4")
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_directory)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Высокое", "Среднее"])
        self.quality_combo.setCurrentText("Высокое")
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(browse_btn)
        file_layout.addWidget(self.quality_combo)
        
        # 6. Добавление выбора директории загрузки
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Папка для загрузки:")
        self.dir_input = QLineEdit()
        self.dir_input.setText(self.download_dir)
        dir_browse_btn = QPushButton("Выбрать...")
        dir_browse_btn.clicked.connect(self.browse_download_dir)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(dir_browse_btn)
        
        # Options
        self.loop_checkbox = QCheckBox("Зациклить видео под длину аудио")
        self.loop_checkbox.setChecked(False)
        
        # Download Button
        download_btn = QPushButton("Скачать Coub")
        download_btn.clicked.connect(self.start_download)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        
        # Log
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        
        # Add widgets to layout
        layout.addLayout(url_layout)
        layout.addLayout(file_layout)
        layout.addLayout(dir_layout)
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(download_btn)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_output)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")

    def browse_directory(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить видео Coub", self.download_dir, "MP4 файлы (*.mp4)")
        if filename:
            self.file_input.setText(os.path.basename(filename))

    def browse_download_dir(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Выберите папку для загрузки", self.download_dir)
        if dir_path:
            self.download_dir = dir_path
            self.dir_input.setText(dir_path)
            if not create_download_directory(self.download_dir):
                QMessageBox.warning(self, "Ошибка", f"Не удалось создать/проверить директорию: {dir_path}")

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.url_input.setText(text)

    def update_filename_from_url(self):
        url = self.url_input.text().strip()
        if url and "coub.com/view/" in url:
            coub_id = url.split('/')[-1]
            self.file_input.setText(f"coub_{coub_id}.mp4")

    def start_download(self):
        if not check_ffmpeg():
            self.status_bar.showMessage("FFmpeg не найден. Установите FFmpeg и добавьте его в PATH.")
            QMessageBox.critical(self, "Ошибка", "FFmpeg не найден. Установите FFmpeg и добавьте его в PATH.")
            return

        coub_url = self.url_input.text().strip()
        filename = self.file_input.text().strip()
        loop = self.loop_checkbox.isChecked()
        quality = "high" if self.quality_combo.currentText() == "Высокое" else "medium"
        self.download_dir = self.dir_input.text().strip()
        
        if not coub_url:
            self.status_bar.showMessage("Ошибка: Введите URL Coub")
            QMessageBox.warning(self, "Ошибка", "Введите URL Coub")
            return
            
        if not filename:
            filename = f"coub_{coub_url.split('/')[-1]}.mp4"
        elif not filename.endswith(".mp4"):
            filename += ".mp4"
        self.file_input.setText(filename)
        
        # 7. Проверка директории перед загрузкой
        if not create_download_directory(self.download_dir):
            self.status_bar.showMessage(f"Ошибка: Невозможно записать в {self.download_dir}")
            QMessageBox.critical(self, "Ошибка", f"Невозможно записать в указанную директорию: {self.download_dir}")
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.log_output.append(f"Начало загрузки: {coub_url}")
        self.status_bar.showMessage("Скачивание видео...")
        
        self.download_thread = DownloadThread(coub_url, filename, loop, quality, self.download_dir)
        self.download_thread.update_signal.connect(self.update_log_and_status)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()
    
    def update_log_and_status(self, message):
        self.log_output.append(message)
        if "Скачивание видео" in message:
            self.status_bar.showMessage("Скачивание видео...")
        elif "Скачивание аудио" in message:
            self.status_bar.showMessage("Скачивание аудио...")
        elif "Зацикливание видео" in message:
            self.status_bar.showMessage("Зацикливание видео...")
        elif "Объединение видео" in message:
            self.status_bar.showMessage("Объединение видео и аудио...")

    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def download_finished(self, success):
        self.progress_bar.setVisible(False)
        if success:
            self.log_output.append("Загрузка успешно завершена!")
            self.status_bar.showMessage("Файл успешно скачан")
            QMessageBox.information(self, "Успех", "Файл успешно скачан")
        else:
            self.log_output.append("Ошибка при загрузке!")
            self.status_bar.showMessage("Ошибка: Не удалось скачать файл")
            QMessageBox.critical(self, "Ошибка", "Не удалось скачать файл")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CoubDownloaderGUI()
    window.show()
    sys.exit(app.exec_())