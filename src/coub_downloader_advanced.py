import requests
import os
import ffmpeg
import logging
import validators
from concurrent.futures import ThreadPoolExecutor
import tempfile
import shutil
import argparse

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Укажите вашу директорию для загрузок
DOWNLOAD_DIR = "D:/CoubDownloads"

def create_download_directory(directory):
    """
    Create the directory for downloading coub videos.

    :param directory: The directory to create.
    :return: None
    """
    if not os.path.exists(directory):
        # Create the directory if it doesn't exist
        os.makedirs(directory)

def get_media_urls(coub_url):
    """
    Get the URLs for the video and audio files for the given coub URL.

    :param coub_url: The URL of the coub video to download.
    :return: A tuple of two strings, the video and audio URLs.
    """
    try:
        # Check if the URL is valid
        if not validators.url(coub_url):
            logging.error("Некорректный URL")
            return None, None

        # Extract the coub ID from the URL
        coub_id = coub_url.split('/')[-1]

        # Construct the API URL for the coub
        api_url = f"https://coub.com/api/v2/coubs/{coub_id}"

        # Set the User-Agent to avoid being blocked by the server
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # Get the JSON response from the API
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()

        # Extract the video and audio URLs from the JSON response
        data = response.json()

        video_versions = data.get('file_versions', {}).get('html5', {})
        video_url = video_versions.get('video', {}).get('high', {}).get('url') or \
                   video_versions.get('video', {}).get('med', {}).get('url')

        audio_url = video_versions.get('audio', {}).get('high', {}).get('url') or \
                   video_versions.get('audio', {}).get('med', {}).get('url')

        # Return None if the URLs could not be found
        if not video_url or not audio_url:
            logging.error("Не удалось найти URL видео или аудио")
            return None, None

        # Return the URLs if we found them
        return video_url, audio_url

    except Exception as e:
        # Print an error if we had an exception
        logging.error(f"Ошибка при получении URL медиа: {e}")
        return None, None

def download_file(url, filepath):
    """
    Download the file from the given URL and save it to the given path.
    
    :param url: The URL of the file to download.
    :param filepath: The path to save the file to.
    :return: True on success, False if there was an error.
    """
    try:
        # Send a GET request to the URL and get the response
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Open the file for writing
        with open(filepath, 'wb') as f:
            # Iterate over the chunks in the response and write them to the file
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        # Return True to indicate success
        return True
    except Exception as e:
        # Print an error message if there was an exception
        logging.error(f"Ошибка при скачивании: {e}")
        # Return False to indicate failure
        return False

def get_duration(file_path):
    """
    Get the duration of the given media file using ffprobe.

    :param file_path: The path to the file to get the duration of.
    :return: The duration of the file in seconds, or None if it cannot be determined.
    """
    try:
        # Attempt to probe the file for stream information
        probe = ffmpeg.probe(file_path)
        
        # Check if streams are present in the probe result
        if 'streams' not in probe or not probe['streams']:
            logging.error("Не удалось определить длительность: отсутствуют потоки")
            return None
        
        # Extract the duration from the first stream
        duration = float(probe['streams'][0]['duration'])
        return duration
    
    except Exception as e:
        # Log an error if an exception occurs during probing
        logging.error(f"Ошибка при определении длительности: {e}")
        return None

def loop_video_to_audio_duration(video_path, audio_path, looped_video_path):
    """
    Loop the video to the length of the audio using FFmpeg.

    :param video_path: The path to the video file.
    :param audio_path: The path to the audio file.
    :param looped_video_path: The path to the output video file.
    :return: True on success, False if there was an error.
    """
    try:
        # Get the durations of the video and audio
        video_duration = get_duration(video_path)
        audio_duration = get_duration(audio_path)
        
        # If either duration is unknown, return an error
        if not video_duration or not audio_duration:
            return False
        
        # If the video is longer or equal to the audio, trim it to the length of the audio
        if video_duration >= audio_duration:
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(stream, looped_video_path, c='copy', t=audio_duration)
            ffmpeg.run(stream, overwrite_output=True)
            return True
        
        # Calculate the number of loops needed to match the length of the audio
        loop_count = int(audio_duration // video_duration) + 1
        
        # Use the concat filter to create a looped video with reencoding
        stream = ffmpeg.input(video_path)
        looped = ffmpeg.concat(*[stream] * loop_count)
        looped = ffmpeg.output(looped, looped_video_path, vcodec='libx264', t=audio_duration)
        ffmpeg.run(looped, overwrite_output=True)
        return True
    
    except Exception as e:
        # Print an error message if an exception occurs
        logging.error(f"Ошибка при зацикливании видео: {e}")
        return False

def merge_video_audio(video_path, audio_path, output_path, loop=False):
    """
    Merge a video and an audio into one file using FFmpeg.

    :param video_path: The path to the video file.
    :param audio_path: The path to the audio file.
    :param output_path: The path to the output file.
    :param loop: Whether to loop the video to the length of the audio.
    :return: True on success, False if there was an error.
    """
    try:
        # Get the video and audio streams
        video_stream = ffmpeg.input(video_path)
        audio_stream = ffmpeg.input(audio_path)

        # Set the output settings
        if loop:
            # If looping is enabled, use the full duration of the audio
            output = ffmpeg.output(video_stream, audio_stream, output_path, 
                                 vcodec='libx264', acodec='aac', strict='experimental')
        else:
            # If looping is disabled, trim the video to the length of the audio
            video_duration = get_duration(video_path)
            output = ffmpeg.output(video_stream, audio_stream, output_path, 
                                 vcodec='libx264', acodec='aac', strict='experimental', t=video_duration)

        # Run FFmpeg and return the result
        ffmpeg.run(output, overwrite_output=True)
        return True
    except Exception as e:
        # Log an error if an exception occurs during the merge
        logging.error(f"Ошибка при объединении: {e}")
        return False

def download_media(video_url, audio_url, temp_video, temp_audio):
    """
    Download the video and audio files using two threads.

    :param video_url: The URL of the video file.
    :param audio_url: The URL of the audio file.
    :param temp_video: The path to the temporary video file.
    :param temp_audio: The path to the temporary audio file.
    :return: True on success, False if there was an error.
    """
    # Create a ThreadPoolExecutor to run the downloads in parallel
    with ThreadPoolExecutor() as executor:
        # Submit the two download tasks to the executor
        futures = [
            executor.submit(download_file, video_url, temp_video),
            executor.submit(download_file, audio_url, temp_audio)
        ]
        # Wait for the results of the two tasks
        for future in futures:
            # If either task failed, return False
            if not future.result():
                return False
    # If both tasks succeeded, return True
    return True

def download_coub(coub_url, filename):
    """
    Download a Coub video, optionally loop the video to the length of the audio, 
    and merge them into a single file.

    :param coub_url: The URL of the Coub video to download.
    :param filename: The name of the output file (including extension).
    :return: True on success, False if there was an error.
    """
    try:
        # Get the video and audio URLs from the Coub URL
        video_url, audio_url = get_media_urls(coub_url)
        if not video_url or not audio_url:
            logging.error("Не удалось найти URL видео или аудио")
            return False

        # Create temporary files for the video and audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video_file:
            temp_video = temp_video_file.name
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
            temp_audio = temp_audio_file.name

        # Download the video and audio files
        logging.info(f"Скачивание видео {filename}...")
        if not download_media(video_url, audio_url, temp_video, temp_audio):
            return False

        # Ask the user if they want to loop the video to match the audio length
        loop_choice = input("Зациклить видео под длину аудио? (y/n): ").lower()
        while loop_choice not in ['y', 'n']:
            loop_choice = input("Пожалуйста, введите 'y' или 'n': ").lower()
        loop = loop_choice == 'y'

        if loop:
            # Loop the video to the length of the audio
            logging.info("Зацикливание видео под длительность аудио...")
            looped_video = os.path.join(DOWNLOAD_DIR, f"looped_video_{filename}")
            if not loop_video_to_audio_duration(temp_video, temp_audio, looped_video):
                return False
            video_to_merge = looped_video
        else:
            # Use the original video
            logging.info("Оставляем одно проигрывание видео...")
            video_to_merge = temp_video

        # Merge the video and audio into a single file
        logging.info("Объединение видео и аудио...")
        final_path = os.path.join(DOWNLOAD_DIR, filename)
        if merge_video_audio(video_to_merge, temp_audio, final_path, loop):
            # Clean up temporary files
            os.remove(temp_video)
            os.remove(temp_audio)
            if loop:
                os.remove(looped_video)
            logging.info(f"Видео со звуком успешно сохранено в {final_path}")
            return True
        return False

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return False

def parse_args():
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: An object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Download a Coub video")
    parser.add_argument(
        "url",
        help="The URL of the Coub video to download"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="The name of the output file (default is the video ID with a .mp4 extension)",
        default=None
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="The directory to save the output file in (default is the current working directory)",
        default=DOWNLOAD_DIR
    )
    return parser.parse_args()

def main():
    """
    Main function to parse arguments, create the download directory, 
    and download the specified Coub video.
    """
    # Parse command line arguments
    args = parse_args()
    
    # Create the download directory if it doesn't exist
    create_download_directory(args.directory)
    
    # Determine the filename for the downloaded video
    filename = args.output if args.output else f"coub_{args.url.split('/')[-1]}.mp4"
    
    # Download the Coub video
    download_coub(args.url, filename)

if __name__ == "__main__":
    main()