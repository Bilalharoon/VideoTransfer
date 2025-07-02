import os
import requests
import json
import sys
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pytubefix import YouTube
from pytubefix.cli import on_progress
# --- Configuration ---
# The SCOPES define what permissions your application requests.
# 'https://www.googleapis.com/auth/photoslibrary.appendonly' allows uploading media.
# 'https://www.googleapis.com/auth/photoslibrary.readonly' allows reading media metadata (useful for checking uploads).
SCOPES = ['https://www.googleapis.com/auth/photoslibrary.appendonly',
          'https://www.googleapis.com/auth/photoslibrary.readonly']

# The name of your credentials file downloaded from Google Cloud Console.
CLIENT_SECRETS_FILE = 'credentials.json'

# The name of the token file where your script will store user credentials after first authentication.
TOKEN_FILE = 'token.json'
PROCESSED_VIDEOS_FILE = 'processed_videos.json'


def load_secrets():
    """
    Loads the secrets from the Secrets.json file.
    This file should contain your API keys and other sensitive information.
    """
    try:
        with open('secrets.json', 'r') as secrets_file:
            return json.load(secrets_file)
    except FileNotFoundError:
        print("Secrets.json file not found. Please create it with your API keys.")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error decoding Secrets.json. Please ensure it is a valid JSON file.")
        sys.exit(1)

secrets = load_secrets()
YOUTUBE_API_KEY = secrets.get('API_KEY')

CHANNELS_TO_WATCH = [
    'UCxi42r9Q2RtW6Hq20FtQu6A',
    'UCWFxT2oy0K9A5PiLdkCXAoQ'  # Example channel ID, replace with actual channel IDs you want to watch
]

CHECK_INTERVAL = 60 * 60  # Check every hour (in seconds)

def authenticate_google_photos():
    """
    Authenticates the user with Google Photos Library API using OAuth 2.0.
    It will try to load existing credentials, or prompt the user to authorize.
    """
    creds = None
    # The token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Create an InstalledAppFlow instance.
            # This will open a browser window for the user to authenticate.
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

def upload_video_to_google_photos(video_path):
    """
    Uploads a video file to Google Photos.

    Args:
        video_path (str): The full path to the video file on your computer.
    """
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at '{video_path}'")
        return

    print(f"Attempting to upload video: {video_path}")

    try:
        # Authenticate and get credentials
        creds = authenticate_google_photos()
        if not creds:
            print("Authentication failed. Please ensure 'credentials.json' is correct and you've authorized the app.")
            return

        # Build the Google Photos API service client
        # We use 'photoslibrary' for the service name and 'v1' for the version.
        service = build('photoslibrary', 'v1', credentials=creds, static_discovery=False)

        # --- Step 1: Upload the media bytes to get an upload token ---
        # The 'upload_endpoint' is a special URL for direct media uploads.
        upload_endpoint = 'https://photoslibrary.googleapis.com/v1/uploads'

        # Read the video file in binary mode
        with open(video_path, 'rb') as f:
            video_bytes = f.read()

        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/octet-stream', # Use octet-stream for raw bytes
            'X-Google-Upload-Content-Type': 'video/*', # Specify the actual media type (e.g., video/mp4, video/quicktime)
            'X-Google-Upload-Protocol': 'raw', # Indicate raw upload protocol
            'X-Goog-Upload-File-Name': os.path.basename(video_path) # Provide original file name
        }

        print("Uploading video bytes to Google Photos...")
        upload_response = requests.post(upload_endpoint, headers=headers, data=video_bytes)

        if upload_response.status_code == 200:
            upload_token = upload_response.text # The response body is the upload token
            print(f"Video bytes uploaded successfully. Upload Token: {upload_token}")
        else:
            print(f"Error uploading video bytes. Status Code: {upload_response.status_code}")
            print(f"Response: {upload_response.text}")
            return

        # --- Step 2: Create a new media item using the upload token ---
        # This step finalizes the upload and adds the item to the user's library.
        new_media_item = {
            'newMediaItems': [
                {
                    'description': f'Uploaded from Python script: {os.path.basename(video_path)}',
                    'simpleMediaItem': {
                        'uploadToken': upload_token
                    }
                }
            ]
        }

        print("Creating new media item in Google Photos library...")
        create_response = service.mediaItems().batchCreate(body=new_media_item).execute()

        # Check the response for success or errors
        if 'newMediaItemResults' in create_response:
            for item_result in create_response['newMediaItemResults']:
                print(f"Processing result for item: {item_result}")
                if item_result['status']['message'] == 'Success':
                    print(f"Successfully uploaded: {item_result['mediaItem']['filename']}")
                    print(f"Google Photos URL: {item_result['mediaItem']['productUrl']}")
                else:
                    error_message = item_result.get('status', {}).get('message', 'Unknown error')
                    print(f"Error creating media item for {os.path.basename(video_path)}: {error_message}")
        else:
            print("Unexpected response from batchCreate:", create_response)

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def build_youtube_service(api_key):
    """
    Builds and returns a YouTube service client using the YouTube Data API v3.
    """
    try:
        return build('youtube', 'v3', developerKey=api_key)
    except Exception as e:
        print(f"Error building YouTube service: {e}")
        return None

def load_processed_videos():
    """
    Loads the list of processed videos from a JSON file.
    If the file does not exist, it returns an empty list.
    """
    try:
        if os.path.exists(PROCESSED_VIDEOS_FILE):
            with open(PROCESSED_VIDEOS_FILE, 'r') as f:
                return json.load(f)
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {PROCESSED_VIDEOS_FILE}. Returning empty list.")
    except Exception as e:
        print(f"Error loading processed videos: {e}")
    return []
def get_latest_video_url(youtube_service, channel_id):
    """
    Fetches the latest video URL from a YouTube channel.

    Args:
        youtube_service: The YouTube service client.
        channel_id (str): The ID of the YouTube channel.

    Returns:
        str: The URL of the latest video, or None if not found.
    """
    try:
        
        request = youtube_service.search().list(
            part='snippet',
            channelId=channel_id,
            order='date',
            maxResults=1,
            type='video'
        )
        response = request.execute()
        if response['items']:
            video_id = response['items'][0]['id']['videoId']
            if video_id not in load_processed_videos():
                return {"Video Title": response['items'][0]['snippet']['title'], 
                        "Video URL": f'https://www.youtube.com/watch?v={video_id}', 
                        "Video ID": video_id}
            print(f"Video {video_id} has already been processed.")
        else:
            print(f"No videos found for channel ID: {channel_id}")
            return None
    except Exception as e:
        print(f"Error fetching latest video URL: {e}")
        return None

def download_youtube_video(url, file_name):
    """
    Downloads a YouTube video from the given URL and saves it with the given file name.

    """
    yt = YouTube(url, on_progress_callback=on_progress)
    print(f"Downloading video: {yt.title}")
    stream = yt.streams.get_highest_resolution()
    stream.download(filename=file_name)
# --- Main execution ---

def download_and_upload_video(url_to_download):
    print("downloading video from YouTube...")
    if not os.path.exists('./downloaded_video.mp4'):
        print("No existing video found. Downloading from YouTube...")
        print(f"downloading video from YouTube...\nURL: {url_to_download}")
        download_youtube_video(url_to_download, 'downloaded_video.mp4')
        print(f"Downloaded video to 'downloaded_video.mp4'")
        # Check if the user has updated the placeholder path
        print("Uploading video to Google Photos...")
        upload_video_to_google_photos(video_path='downloaded_video.mp4')
        os.remove('downloaded_video.mp4')  # Clean up the downloaded video file
        print("Video upload completed and temporary file removed.")
    else:
        print("A video file already exists. Skipping download and upload.")
        print("If you want to re-upload, please delete 'downloaded_video.mp4' first.")
        sys.exit(0)
if __name__ == '__main__':
    # Replace with the actual path to your video file
    # Example: video_file_to_upload = "C:/Users/YourUser/Videos/my_awesome_video.mp4"
    # Or for a relative path: video_file_to_upload = "my_video.mov"
    if len(sys.argv) > 2:
        download_and_upload_video(sys.argv[1])
    elif len(sys.argv) == 1:
        print(f"No video URL provided. Watching {len(CHANNELS_TO_WATCH)} YouTube channels for new videos...")
        youtube_service = build_youtube_service(YOUTUBE_API_KEY)
        if not youtube_service:
            print("Failed to build YouTube service. Exiting.")
            sys.exit(1)
        
        while True:
            for channel_id in CHANNELS_TO_WATCH:
                video_info = get_latest_video_url(youtube_service, channel_id)
                latest_video_url = video_info.get("Video URL")
                latest_video_title = video_info.get("Video Title")
                latest_video_id = video_info.get("Video ID")
                if latest_video_url:
                    print(f"Latest video title for channel {channel_id}: {latest_video_title}")
                    print(f"Latest video URL for channel {channel_id}: {latest_video_url}")
                    # Download and upload the video
                    download_and_upload_video(latest_video_url)    
                    #add video to processed list
                    processed_videos = load_processed_videos()
                    processed_videos.append(latest_video_id)  # Extract video ID from URL
                    with open(PROCESSED_VIDEOS_FILE, 'w') as processed_file:
                        json.dump(processed_videos, processed_file)
                    print(f"Video {latest_video_id} has been processed and added to the list.") 
                else:
                    print(f"No new videos found for channel {channel_id}.") 
            print(f"Waiting for {CHECK_INTERVAL // 60} minutes before checking again...")
            # Wait for the specified interval before checking again
            # This is to avoid hitting the YouTube API rate limits.
            time.sleep(CHECK_INTERVAL) 
    else:
        print("Invalid number of arguments. Please provide a YouTube video URL to download and upload, or run without arguments to watch channels for new videos.")
        sys.exit(1)
