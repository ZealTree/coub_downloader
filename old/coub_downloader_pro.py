import argparse
import requests
import os
import ffmpeg
import logging
from concurrent.futures import ThreadPoolExecutor
import tempfile
from tqdm import tqdm
import subprocess

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Укажите вашу директорию для загрузок
DOWNLOAD_DIR = "D:/CoubDownloads"

# Доступные видеокодеки
SUPPORTED_VCODECS = {
    'h264': ['libx264', 'h264_amf', 'h264_qsv', 'h264_nvenc'],
    'hevc': ['libx265', 'hevc_amf', 'hevc_qsv', 'hevc_nvenc'],
    'av1': ['libaom-av1', 'av1_qsv']
}

def parse_args():
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(description='Скачивание видео с Coub')
    parser.add_argument('-v', '--vcodec', 
                       choices=[codec for group in SUPPORTED_VCODECS.values() for codec in group],
                       default='libx264',
                       help='Выбор видеокодека (по умолчанию: libx264)')
    parser.add_argument('-p', '--proxy', 
                       type=str,
                       help='Прокси в формате http://user:password@host:port')
    return parser.parse_args()

def create_download_directory():
    """Создание директории для загрузок, если она не существует."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

def is_valid_url(url):
    """Проверка корректности URL Coub."""
    return url.startswith('https://coub.com/view/')

def check_ffmpeg_and_codec(vcodec):
    """Проверка наличия FFmpeg и поддержки указанного кодека."""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("FFmpeg не найден в системе. Установите FFmpeg и добавьте его в PATH.")
        return False
    
    try:
        result = subprocess.run(['ffmpeg', '-codecs'], capture_output=True, text=True, check=True)
        if vcodec not in result.stdout:
            logging.error(f"Кодек {vcodec} не поддерживается вашей версией FFmpeg.")
            return False
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Ошибка при проверке кодеков FFmpeg: {e}")
        return False

def get_media_urls(coub_url, proxy=None):
    """Получение URL видео и аудио из API Coub."""
    try:
        if not is_valid_url(coub_url):
            logging.error("Некорректный URL Coub. Ожидается ссылка вида: https://coub.com/view/...")
            return None, None

        coub_id = coub_url.split('/')[-1]
        if not coub_id:
            logging.error("Не удалось извлечь ID из URL Coub")
            return None, None

        api_url = f"https://coub.com/api/v2/coubs/{coub_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        
        response = requests.get(api_url, headers=headers, proxies=proxies)
        response.raise_for_status()
        
        data = response.json()
        
        video_versions = data.get('file_versions', {}).get('html5', {})
        video_url = video_versions.get('video', {}).get('high', {}).get('url') or \
                   video_versions.get('video', {}).get('med', {}).get('url')
        
        audio_url = video_versions.get('audio', {}).get('high', {}).get('url') or \
                   video_versions.get('audio', {}).get('med', {}).get('url')
        
        if not video_url or not audio_url:
            logging.error("Не удалось найти URL видео или аудио в ответе API")
            return None, None
            
        return video_url, audio_url
        
    except Exception as e:
        logging.error(f"Ошибка при получении URL медиа: {str(e)}")
        return None, None

def download_file(url, filepath, proxy=None):
    """Скачивание файла с индикатором прогресса."""
    try:
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        response = requests.get(url, stream=True, proxies=proxies)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        with open(filepath, 'wb') as f, tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(filepath)) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        return True
    except Exception as e:
        logging.error(f"Ошибка при скачивании: {e}")
        return False

def get_duration(file_path):
    """Получение длительности файла."""
    try:
        probe = ffmpeg.probe(file_path)
        if 'streams' not in probe or not probe['streams']:
            logging.error("Не удалось определить длительность: отсутствуют потоки")
            return None
        duration = float(probe['streams'][0]['duration'])
        return duration
    except Exception as e:
        logging.error(f"Ошибка при определении длительности: {e}")
        return None

def loop_video_to_audio_duration(video_path, audio_path, looped_video_path, vcodec):
    """Зацикливание видео под длительность аудио."""
    try:
        video_duration = get_duration(video_path)
        audio_duration = get_duration(audio_path)
        
        if not video_duration or not audio_duration:
            return False
            
        if video_duration >= audio_duration:
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(stream, looped_video_path, c='copy', t=audio_duration)
            ffmpeg.run(stream, overwrite_output=True)
            return True
            
        loop_count = int(audio_duration // video_duration) + 1
        stream = ffmpeg.input(video_path)
        looped = ffmpeg.concat(*[stream] * loop_count)
        looped = ffmpeg.output(looped, looped_video_path, vcodec=vcodec, t=audio_duration)
        ffmpeg.run(looped, overwrite_output=True)
        return True
    except Exception as e:
        logging.error(f"Ошибка при зацикливании видео: {e}")
        return False

def merge_video_audio(video_path, audio_path, output_path, loop=False, vcodec='libx264'):
    """Объединение видео и аудио."""
    try:
        video_stream = ffmpeg.input(video_path)
        audio_stream = ffmpeg.input(audio_path)
        
        if loop:
            output = ffmpeg.output(video_stream, audio_stream, output_path, 
                                 vcodec=vcodec, acodec='aac', strict='experimental')
        else:
            video_duration = get_duration(video_path)
            output = ffmpeg.output(video_stream, audio_stream, output_path, 
                                 vcodec=vcodec, acodec='aac', strict='experimental', t=video_duration)
        ffmpeg.run(output, overwrite_output=True)
        return True
    except Exception as e:
        logging.error(f"Ошибка при объединении: {e}")
        return False

def download_media(video_url, audio_url, temp_video, temp_audio, proxy=None):
    """Параллельное скачивание видео и аудио."""
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(download_file, video_url, temp_video, proxy),
            executor.submit(download_file, audio_url, temp_audio, proxy)
        ]
        for future in futures:
            if not future.result():
                return False
    return True

def download_coub(coub_url, filename_base, vcodec='libx264', proxy=None):
    """Основная функция скачивания и обработки Coub."""
    temp_video = temp_audio = looped_video = None
    try:
        video_url, audio_url = get_media_urls(coub_url, proxy)
        if not video_url or not audio_url:
            logging.error("Не удалось найти URL видео или аудио")
            return False

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video_file:
            temp_video = temp_video_file.name
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
            temp_audio = temp_audio_file.name

        logging.info(f"Скачивание видео {filename_base} с кодеком {vcodec}...")
        if not download_media(video_url, audio_url, temp_video, temp_audio, proxy):
            return False
            
        max_attempts = 3
        for attempt in range(max_attempts):
            loop_choice = input("Зациклить видео под длину аудио? (y/n): ").lower()
            if loop_choice in ['y', 'n']:
                break
            logging.warning(f"Некорректный ввод. Осталось попыток: {max_attempts - attempt - 1}")
        else:
            logging.error("Превышено количество попыток ввода. Используется значение по умолчанию: 'n'")
            loop_choice = 'n'
        loop = loop_choice == 'y'
        
        final_filename = f"{filename_base}_{vcodec}.mp4"
        final_path = os.path.join(DOWNLOAD_DIR, final_filename)
        
        if os.path.exists(final_path):
            overwrite = input(f"Файл {final_filename} уже существует. Перезаписать? (y/n): ").lower()
            if overwrite != 'y':
                final_filename = f"{filename_base}_{vcodec}_{os.urandom(4).hex()}.mp4"
                final_path = os.path.join(DOWNLOAD_DIR, final_filename)

        if loop:
            logging.info("Зацикливание видео под длительность аудио...")
            looped_video = os.path.join(DOWNLOAD_DIR, f"looped_video_{filename_base}.mp4")
            if not loop_video_to_audio_duration(temp_video, temp_audio, looped_video, vcodec):
                return False
            video_to_merge = looped_video
        else:
            logging.info("Оставляем одно проигрывание видео...")
            video_to_merge = temp_video
            
        logging.info(f"Объединение видео и аудио с кодеком {vcodec}...")
        if merge_video_audio(video_to_merge, temp_audio, final_path, loop, vcodec):
            logging.info(f"Видео со звуком успешно сохранено в {final_path}")
            return True
        return False
        
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return False
    finally:
        for file in (temp_video, temp_audio, looped_video):
            if file and os.path.exists(file):
                os.remove(file)

def main():
    args = parse_args()
    create_download_directory()
    
    if not check_ffmpeg_and_codec(args.vcodec):
        print("Проверьте наличие FFmpeg и поддержку кодека.")
        return
    
    while True:
        coub_url = input("Введите URL coub видео (или 'exit' для выхода): ").strip()
        
        if coub_url.lower() == 'exit':
            break
            
        if not is_valid_url(coub_url):
            print("Пожалуйста, введите корректный URL Coub в формате: https://coub.com/view/xxxxxx")
            continue
            
        filename_base = f"coub_{coub_url.split('/')[-1]}"
        if download_coub(coub_url, filename_base, args.vcodec, args.proxy):
            print("Успешно скачан!")
        else:
            print("Не удалось скачать Coub")

if __name__ == "__main__":
    main()