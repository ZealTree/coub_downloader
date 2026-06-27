import sys
import os
import shutil
import subprocess
import re
from urllib.parse import urlparse
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, 
                             QFileDialog, QTextEdit, QStatusBar, QComboBox, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon
import requests
import ffmpeg

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "CoubDownloads")

def create_download_directory(directory):
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
        test_file = os.path.join(directory, "test_permission")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception as e:
        print(f"Ошибка при создании/проверке директории: {e}")
        return False

def check_ffmpeg():
    try:
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            return False
        result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        return result.returncode == 0
    except Exception as e:
        print(f"Ошибка при проверке FFmpeg: {e}")
        return False

def get_media_urls(coub_url, quality="high"):
    try:
        # Теперь регулярное выражение работает идеально
        match = re.search(r'view/([a-zA-Z0-9]+)', coub_url)
        if not match:
            parsed_path = urlparse(coub_url).path.strip('/')
            coub_id = parsed_path.split('/')[-1] if parsed_path else coub_url
        else:
            coub_id = match.group(1)

        api_url = f"https://coub.com/api/v2/coubs/{coub_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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
        
    except Exception as e:
        print(f"Ошибка получения медиа-URL: {e}")
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

    def run_ffmpeg_subprocess(self, cmd, task_name, start_progress, progress_weight, total_duration):
        self.update_signal.emit(f"Запуск: {task_name}...")
        full_cmd = ['ffmpeg'] + cmd
        process = subprocess.Popen(
            full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
            text=True, encoding='utf-8', errors='replace', bufsize=1
        )

        for line in process.stdout:
            self.update_signal.emit(line.strip())
            if "out_time=" in line and total_duration:
                try:
                    time_str = line.split("out_time=")[-1].split()[0]
                    h, m, s = time_str.split(':')
                    seconds = int(h) * 3600 + int(m) * 60 + float(s)
                    stage_p = min(seconds / total_duration, 1.0)
                    actual_p = int(start_progress + (stage_p * progress_weight))
                    self.progress_signal.emit(actual_p)
                except:
                    pass

        process.wait()
        return process.returncode == 0

    def run(self):
        temp_video = os.path.join(self.download_dir, f"temp_video_{self.filename}")
        temp_audio = os.path.join(self.download_dir, f"temp_audio_{self.filename}")
        looped_video = os.path.join(self.download_dir, f"looped_video_{self.filename}")
        final_path = os.path.join(self.download_dir, self.filename)

        try:
            video_url, audio_url = get_media_urls(self.coub_url, self.quality)
            if not video_url or not audio_url:
                self.update_signal.emit("Не удалось получить ссылки на медиа")
                self.finished_signal.emit(False)
                return

            self.update_signal.emit("Скачивание видео...")
            for progress in download_file(video_url, temp_video):
                if progress == -1:
                    self.finished_signal.emit(False)
                    return
                self.progress_signal.emit(int(progress * 0.4))
            
            self.update_signal.emit("Скачивание аудио...")
            for progress in download_file(audio_url, temp_audio):
                if progress == -1:
                    self.finished_signal.emit(False)
                    return
                self.progress_signal.emit(int(40 + progress * 0.4))

            video_duration = self.get_duration(temp_video)
            audio_duration = self.get_duration(temp_audio)

            if not video_duration or not audio_duration:
                self.update_signal.emit("Ошибка определения длительности медиафайлов")
                self.finished_signal.emit(False)
                return

            video_to_merge = temp_video

            if self.loop:
                if video_duration >= audio_duration:
                    cmd = ['-y', '-i', temp_video, '-c', 'copy', '-t', str(audio_duration), looped_video]
                else:
                    loop_count = int(audio_duration // video_duration) + 1
                    cmd = ['-y', '-stream_loop', str(loop_count), '-i', temp_video, '-c:v', 'libx264', '-t', str(audio_duration), looped_video]
                
                success = self.run_ffmpeg_subprocess(cmd, "Зацикливание видео", 80, 10, audio_duration)
                if not success:
                    self.finished_signal.emit(False)
                    return
                video_to_merge = looped_video
            else:
                self.progress_signal.emit(90)

            final_duration = audio_duration if self.loop else video_duration
            cmd = ['-y', '-i', video_to_merge, '-i', temp_audio, '-c:v', 'libx264', '-c:a', 'aac', '-t', str(final_duration), final_path]
            
            success = self.run_ffmpeg_subprocess(cmd, "Объединение потоков", 90, 10, final_duration)
            self.cleanup_temp_files(temp_video, temp_audio, looped_video)
            
            if success:
                self.progress_signal.emit(100)
                self.finished_signal.emit(True)
            else:
                self.finished_signal.emit(False)

        except Exception as e:
            self.update_signal.emit(f"Критическая ошибка в потоке: {e}")
            self.cleanup_temp_files(temp_video, temp_audio, looped_video)
            self.finished_signal.emit(False)

    def get_duration(self, file_path):
        try:
            probe = ffmpeg.probe(file_path)
            return float(probe['streams'][0]['duration'])
        except Exception as e:
            self.update_signal.emit(f"Ошибка получения длительности: {e}")
            return None

    def cleanup_temp_files(self, *files):
        for file in files:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except:
                    pass

class CoubDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Загрузчик Coub")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon("icon.ico"))
        self.download_dir = DEFAULT_DOWNLOAD_DIR
        self.init_ui()
        if not create_download_directory(self.download_dir):
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать директорию: {self.download_dir}")

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()
        
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
        
        file_layout = QHBoxLayout()
        file_label = QLabel("Имя файла:")
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("output.mp4")
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_directory)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Высокое", "Среднее"])
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(browse_btn)
        file_layout.addWidget(self.quality_combo)
        
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Папка для загрузки:")
        self.dir_input = QLineEdit()
        self.dir_input.setText(self.download_dir)
        dir_browse_btn = QPushButton("Выбрать...")
        dir_browse_btn.clicked.connect(self.browse_download_dir)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(dir_browse_btn)
        
        self.loop_checkbox = QCheckBox("Зациклить видео под длину аудио")
        self.download_btn = QPushButton("Скачать Coub")
        self.download_btn.clicked.connect(self.start_download)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        
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
        self.status_bar.showMessage("Готов к работе")

    def browse_directory(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить видео Coub", self.download_dir, "MP4 файлы (*.mp4)")
        if filename:
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
        if not check_ffmpeg():
            QMessageBox.critical(self, "Ошибка", "FFmpeg не найден в системе!")
            return

        coub_url = self.url_input.text().strip()
        filename = self.file_input.text().strip()
        loop = self.loop_checkbox.isChecked()
        quality = "high" if self.quality_combo.currentText() == "Высокое" else "medium"
        self.download_dir = self.dir_input.text().strip()
        
        if not coub_url:
            QMessageBox.warning(self, "Ошибка", "Введите URL Coub")
            return
            
        if not filename:
            match = re.search(r'view/([a-zA-Z0-9]+)', coub_url)
            filename = f"coub_{match.group(1)}.mp4" if match else "coub_output.mp4"
        elif not filename.endswith(".mp4"):
            filename += ".mp4"
        self.file_input.setText(filename)
        
        if not create_download_directory(self.download_dir):
            QMessageBox.critical(self, "Ошибка", f"Нет прав на запись в папку: {self.download_dir}")
            return
        
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.log_output.append(f"\nНачало загрузки: {coub_url}")
        
        self.download_thread = DownloadThread(coub_url, filename, loop, quality, self.download_dir)
        self.download_thread.update_signal.connect(self.update_log_and_status)
        self.download_thread.progress_signal.connect(self.progress_bar.setValue)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()
    
    def update_log_and_status(self, message):
        self.log_output.append(message)
        if "Скачивание" in message or "Зацикливание" in message or "Объединение" in message:
            self.status_bar.showMessage(message)

    def download_finished(self, success):
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        
        if success:
            self.status_bar.showMessage("Файл успешно скачан")
            QMessageBox.information(self, "Успех", "Файл успешно сохранен!")
        else:
            self.status_bar.showMessage("Ошибка при скачивании")
            QMessageBox.critical(self, "Ошибка", "Не удалось скачать или обработать файл.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CoubDownloaderGUI()
    window.show()
    sys.exit(app.exec_())