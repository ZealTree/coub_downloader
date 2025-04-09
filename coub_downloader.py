# coub_downloader_gui.py
import sys
import os
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, 
                            QFileDialog, QMessageBox, QTextEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot
import requests
import ffmpeg
import subprocess
import re

DOWNLOAD_DIR = "D:/CoubDownloads"

def create_download_directory():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

def get_media_urls(coub_url):
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
        video_url = video_versions.get('video', {}).get('high', {}).get('url') or \
                   video_versions.get('video', {}).get('med', {}).get('url')
        
        audio_url = video_versions.get('audio', {}).get('high', {}).get('url') or \
                   video_versions.get('audio', {}).get('med', {}).get('url')
        
        if not video_url or not audio_url:
            return None, None
            
        return video_url, audio_url
        
    except Exception as e:
        print(f"Ошибка при получении URL медиа: {e}")
        return None, None

def download_file(url, filepath, progress_callback=None):
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
                    if progress_callback:
                        progress = int((downloaded / total_size) * 100) if total_size > 0 else 0
                        progress_callback(progress)
        return True
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
        return False

class FFmpegWorker(QObject):
    progress_updated = pyqtSignal(int)
    message_emitted = pyqtSignal(str)
    finished = pyqtSignal(bool)

    @pyqtSlot(str, list, str, float)
    def run_ffmpeg(self, task_name, command, output_file, duration):
        try:
            self.message_emitted.emit(f"Starting {task_name}...")
            
            # Запускаем ffmpeg с прогрессом
            process = subprocess.Popen(
                ['ffmpeg'] + command,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Регулярное выражение для парсинга прогресса
            duration_re = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
            
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                    
                # Парсим прогресс
                match = duration_re.search(line)
                if match:
                    hours, minutes, seconds = match.groups()
                    current_time = int(hours)*3600 + int(minutes)*60 + float(seconds)
                    progress = int((current_time / duration) * 100) if duration > 0 else 0
                    self.progress_updated.emit(progress)
                
                self.message_emitted.emit(line.strip())

            process.wait()
            
            if process.returncode == 0:
                self.message_emitted.emit(f"{task_name} completed successfully")
                self.finished.emit(True)
            else:
                self.message_emitted.emit(f"{task_name} failed with exit code {process.returncode}")
                self.finished.emit(False)
                
        except Exception as e:
            self.message_emitted.emit(f"Error in {task_name}: {str(e)}")
            self.finished.emit(False)

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)

    def __init__(self, coub_url, filename, loop):
        super().__init__()
        self.coub_url = coub_url
        self.filename = filename
        self.loop = loop
        self.ffmpeg_worker = None

    def run(self):
        try:
            video_url, audio_url = get_media_urls(self.coub_url)
            if not video_url or not audio_url:
                self.update_signal.emit("Failed to get media URLs")
                self.finished_signal.emit(False)
                return

            temp_video = os.path.join(DOWNLOAD_DIR, f"temp_video_{self.filename}")
            temp_audio = os.path.join(DOWNLOAD_DIR, f"temp_audio_{self.filename}")
            looped_video = os.path.join(DOWNLOAD_DIR, f"looped_video_{self.filename}")
            final_path = os.path.join(DOWNLOAD_DIR, self.filename)

            # Download video with progress
            self.update_signal.emit("Downloading video...")
            if not download_file(video_url, temp_video, lambda p: self.progress_signal.emit(p)):
                self.finished_signal.emit(False)
                return
            
            # Download audio with progress
            self.update_signal.emit("Downloading audio...")
            if not download_file(audio_url, temp_audio, lambda p: self.progress_signal.emit(p)):
                self.finished_signal.emit(False)
                return

            # Get durations
            video_duration = self.get_duration(temp_video)
            audio_duration = self.get_duration(temp_audio)
            
            if not video_duration or not audio_duration:
                self.finished_signal.emit(False)
                return

            if self.loop:
                self.update_signal.emit("Looping video to match audio duration...")
                
                if video_duration >= audio_duration:
                    # Trim video to audio length
                    cmd = [
                        '-y', '-i', temp_video,
                        '-c', 'copy',
                        '-t', str(audio_duration),
                        looped_video
                    ]
                    task_name = "Trimming video"
                    duration = audio_duration
                else:
                    # Loop video
                    loop_count = int(audio_duration // video_duration) + 1
                    cmd = [
                        '-y',
                        '-stream_loop', str(loop_count),
                        '-i', temp_video,
                        '-c:v', 'libx264',
                        '-t', str(audio_duration),
                        looped_video
                    ]
                    task_name = "Looping video"
                    duration = audio_duration
                
                # Создаем FFmpegWorker в основном потоке
                self.ffmpeg_worker = FFmpegWorker()
                self.ffmpeg_worker.moveToThread(QApplication.instance().thread())
                self.ffmpeg_worker.message_emitted.connect(self.update_signal)
                self.ffmpeg_worker.progress_updated.connect(self.progress_signal)
                
                # Используем прямой вызов вместо сигналов для избежания проблем с потоками
                self.ffmpeg_worker.run_ffmpeg(task_name, cmd, looped_video, duration)
                
                video_to_merge = looped_video
            else:
                video_to_merge = temp_video

            # Merge video and audio
            self.update_signal.emit("Merging video and audio...")
            merge_duration = self.get_duration(video_to_merge)
            cmd = [
                '-y', '-i', video_to_merge,
                '-i', temp_audio,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-strict', 'experimental',
                '-t', str(merge_duration),
                final_path
            ]
            
            # Создаем новый FFmpegWorker для слияния
            self.ffmpeg_worker = FFmpegWorker()
            self.ffmpeg_worker.moveToThread(QApplication.instance().thread())
            self.ffmpeg_worker.message_emitted.connect(self.update_signal)
            self.ffmpeg_worker.progress_updated.connect(self.progress_signal)
            self.ffmpeg_worker.run_ffmpeg("Merging streams", cmd, final_path, merge_duration)
            
            # Cleanup temp files
            os.remove(temp_video)
            os.remove(temp_audio)
            if self.loop:
                os.remove(looped_video)
                
            self.finished_signal.emit(True)

        except Exception as e:
            self.update_signal.emit(f"Error: {e}")
            self.finished_signal.emit(False)

    def get_duration(self, file_path):
        try:
            probe = ffmpeg.probe(file_path)
            duration = float(probe['streams'][0]['duration'])
            return duration
        except Exception as e:
            self.update_signal.emit(f"Error getting duration: {e}")
            return None

class CoubDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coub Downloader")
        self.setGeometry(100, 100, 800, 600)
        self.init_ui()
        create_download_directory()

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # URL Input
        url_layout = QHBoxLayout()
        url_label = QLabel("Coub URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://coub.com/view/...")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        
        # Filename Input
        file_layout = QHBoxLayout()
        file_label = QLabel("Filename:")
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("output.mp4")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_directory)
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(browse_btn)
        
        # Options
        self.loop_checkbox = QCheckBox("Loop video to match audio length")
        self.loop_checkbox.setChecked(False)
        
        # Download Button
        download_btn = QPushButton("Download Coub")
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
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(download_btn)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_output)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        
    def browse_directory(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Coub Video", DOWNLOAD_DIR, "MP4 Files (*.mp4)")
        if filename:
            self.file_input.setText(os.path.basename(filename))
    
    def start_download(self):
        coub_url = self.url_input.text().strip()
        filename = self.file_input.text().strip()
        loop = self.loop_checkbox.isChecked()
        
        if not coub_url:
            QMessageBox.warning(self, "Error", "Please enter a Coub URL")
            return
            
        if not filename:
            filename = f"coub_{coub_url.split('/')[-1]}.mp4"
            self.file_input.setText(filename)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.log_output.append(f"Starting download: {coub_url}")
        
        self.download_thread = DownloadThread(coub_url, filename, loop)
        self.download_thread.update_signal.connect(self.update_log)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()
    
    def update_log(self, message):
        self.log_output.append(message)
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def download_finished(self, success):
        self.progress_bar.setVisible(False)
        if success:
            self.log_output.append("Download completed successfully!")
            QMessageBox.information(self, "Success", "Coub downloaded successfully!")
        else:
            self.log_output.append("Download failed!")
            QMessageBox.warning(self, "Error", "Failed to download Coub")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CoubDownloaderGUI()
    window.show()
    sys.exit(app.exec_())