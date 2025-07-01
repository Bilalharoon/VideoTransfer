import os
import requests
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import sys
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

def download_youtube_video(url, file_name):
    """
    Downloads a YouTube video from the given URL and saves it with the given file name.

    """
    yt = YouTube(url, on_progress_callback=on_progress)
    print(f"Downloading video: {yt.title}")
    stream = yt.streams.get_highest_resolution()
    stream.download(filename=file_name)
# --- Main execution ---
if __name__ == '__main__':
    # Replace with the actual path to your video file
    # Example: video_file_to_upload = "C:/Users/YourUser/Videos/my_awesome_video.mp4"
    # Or for a relative path: video_file_to_upload = "my_video.mov"
    url_to_download = sys.argv[1] # <--- IMPORTANT: CHANGE THIS LINE
    if not os.path.exists('./downloaded_video.mp4'):
        print("No existing video found. Downloading from YouTube...")
        print(f"downloading video from YouTube...\nURL: {url_to_download}")
        download_youtube_video(url_to_download, 'downloaded_video.mp4')
        print(f"Downloaded video to 'downloaded_video.mp4'")
    # Check if the user has updated the placeholder path
    print("Uploading video to Google Photos...")
    upload_video_to_google_photos(video_path='downloaded_video.mp4')

