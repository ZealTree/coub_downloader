import requests
import os
import ffmpeg

# Укажите вашу директорию для загрузок
DOWNLOAD_DIR = "D:/CoubDownloads"

def create_download_directory():
    """
    Create the directory for downloading coub videos.
    
    :return: None
    """
    if not os.path.exists(DOWNLOAD_DIR):
        # Create the directory if it doesn't exist
        os.makedirs(DOWNLOAD_DIR)

def get_media_urls(coub_url):
    """
    Get the URLs for the video and audio files for the given coub URL.
    
    :param coub_url: The URL of the coub video to download.
    :return: A tuple of two strings, the video and audio URLs.
    """
    try:
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
        data = response.json()
        # Extract the video and audio URLs from the JSON response
        video_versions = data.get('file_versions', {}).get('html5', {})
        video_url = video_versions.get('video', {}).get('high', {}).get('url') or \
                   video_versions.get('video', {}).get('med', {}).get('url')
        
        audio_url = video_versions.get('audio', {}).get('high', {}).get('url') or \
                   video_versions.get('audio', {}).get('med', {}).get('url')
        
        if not video_url or not audio_url:
            # If we can't find the URLs, return None
            return None, None
            
        # Return the URLs if we found them
        return video_url, audio_url
        
    except Exception as e:
        # Print an error if we had an exception
        print(f"Ошибка при получении URL медиа: {e}")
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
        print(f"Ошибка при скачивании: {e}")
        # Return False to indicate failure
        return False

def get_duration(file_path):
    """
    Get the duration of the given media file.
    
    :param file_path: The path to the file to get the duration of.
    :return: The duration of the file in seconds.
    """
    try:
        # Use ffprobe to get the duration of the file
        probe = ffmpeg.probe(file_path)
        duration = float(probe['streams'][0]['duration'])
        # Return the duration
        return duration
    except Exception as e:
        # Print an error message if there was an exception
        print(f"Ошибка при определении длительности: {e}")
        # Return None to indicate failure
        return None

def loop_video_to_audio_duration(video_path, audio_path, looped_video_path):
    """
    Loop a video to the length of the audio.
    
    :param video_path: The path to the video file.
    :param audio_path: The path to the audio file.
    :param looped_video_path: The path to the output video file.
    :return: True on success, False if there was an error.
    """
    try:
        video_duration = get_duration(video_path)
        audio_duration = get_duration(audio_path)
        
        if not video_duration or not audio_duration:
            return False
        
        if video_duration >= audio_duration:
            # If the video is longer or equal to the audio, trim it to the length of the audio
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(stream, looped_video_path, c='copy', t=audio_duration)
            ffmpeg.run(stream, overwrite_output=True)
        else:
            # Calculate the number of loops needed
            loop_count = int(audio_duration // video_duration) + 1
            # Use the concat filter to create a looped video with reencoding
            stream = ffmpeg.input(video_path)
            looped = ffmpeg.concat(*[stream] * loop_count)
            looped = ffmpeg.output(looped, looped_video_path, vcodec='libx264', t=audio_duration)
            ffmpeg.run(looped, overwrite_output=True)
        return True
    except Exception as e:
        print(f"Ошибка при зацикливании видео: {e}")
        return False

def merge_video_audio(video_path, audio_path, output_path, loop=False):
    """
    Merge a video and an audio into one file.
    
    :param video_path: The path to the video file.
    :param audio_path: The path to the audio file.
    :param output_path: The path to the output file.
    :param loop: Whether to loop the video to the length of the audio.
    :return: True on success, False if there was an error.
    """
    try:
        video_stream = ffmpeg.input(video_path)
        audio_stream = ffmpeg.input(audio_path)
        
        if loop:
            # If looping is enabled, use the full duration of the audio
            output = ffmpeg.output(video_stream, audio_stream, output_path, 
                                 vcodec='libx264', acodec='aac', strict='experimental')
        else:
            # If looping is disabled, trim the video to the length of the audio
            video_duration = get_duration(video_path)
            output = ffmpeg.output(video_stream, audio_stream, output_path, 
                                 vcodec='libx264', acodec='aac', strict='experimental', t=video_duration)
        ffmpeg.run(output, overwrite_output=True)
        return True
    except Exception as e:
        print(f"Ошибка при объединении: {e}")
        return False

def download_coub(coub_url, filename):
    """
    Download a coub video and its audio, optionally loop the video to the length of the audio, 
    and merge them into a single file.

    :param coub_url: The URL of the coub video to download.
    :param filename: The name of the output file (including extension).
    :return: True on success, False if there was an error.
    """
    try:
        # Get the video and audio URLs from the coub URL
        video_url, audio_url = get_media_urls(coub_url)
        if not video_url or not audio_url:
            print("Не удалось найти URL видео или аудио")
            return False

        # Define temporary paths for video and audio files
        temp_video = os.path.join(DOWNLOAD_DIR, f"temp_video_{filename}")
        temp_audio = os.path.join(DOWNLOAD_DIR, f"temp_audio_{filename}")
        looped_video = os.path.join(DOWNLOAD_DIR, f"looped_video_{filename}")
        final_path = os.path.join(DOWNLOAD_DIR, filename)

        # Download the video file
        print(f"Скачивание видео {filename}...")
        if not download_file(video_url, temp_video):
            return False

        # Download the audio file
        print(f"Скачивание аудио {filename}...")
        if not download_file(audio_url, temp_audio):
            return False

        # Ask the user if they want to loop the video to match the audio length
        loop_choice = input("Зациклить видео под длину аудио? (y/n): ").lower()
        loop = loop_choice == 'y'

        if loop:
            # Loop the video to the length of the audio
            print("Зацикливание видео под длительность аудио...")
            if not loop_video_to_audio_duration(temp_video, temp_audio, looped_video):
                return False
            video_to_merge = looped_video
        else:
            # Use the original video
            print("Оставляем одно проигрывание видео...")
            video_to_merge = temp_video

        # Merge the video and audio into a single file
        print("Объединение видео и аудио...")
        if merge_video_audio(video_to_merge, temp_audio, final_path, loop):
            # Remove temporary files
            os.remove(temp_video)
            os.remove(temp_audio)
            if loop:
                os.remove(looped_video)
            print(f"Видео со звуком успешно сохранено в {final_path}")
            return True

        return False

    except Exception as e:
        # Print an error message if an exception occurs
        print(f"Ошибка: {e}")
        return False

def main():
    """
    Main function that creates the download directory and enters an infinite loop to download Coubs.
    """
    create_download_directory()
    
    while True:
        # Ask the user for the URL of the Coub video to download
        coub_url = input("Введите URL coub видео (или 'exit' для выхода): ")
        
        # Check if the user wants to exit
        if coub_url.lower() == 'exit':
            break
            
        # Create the filename for the downloaded file
        filename = f"coub_{coub_url.split('/')[-1]}.mp4"
        
        # Download the Coub video
        download_coub(coub_url, filename)

if __name__ == "__main__":
    main()