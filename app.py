"""
Video Highlights Generator using Streamlit and Vertex AI Gemini
"""

import os
import json
import tempfile
from datetime import datetime
import streamlit as st
from google.cloud import storage
from vertex_libs.gemini_client import GeminiClient
from google.api_core import exceptions as google_exceptions
from typing import Optional
from dotenv import load_dotenv
import subprocess
from pathlib import Path

# Load environment variables from .env file in development
if os.path.exists(".env"):
    load_dotenv()

# Initialize Vertex AI client
gemini_client = GeminiClient()

# Get environment variables with defaults for Cloud Run
bucket_name = os.environ.get("GCP_BUCKET_NAME")
project_id = os.environ.get("GCP_PROJECT")

# Configure Streamlit
st.set_page_config(
    page_title="Video Highlights Generator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add health check endpoint for Cloud Run
def check_health():
    return {"status": "healthy"}

# Add debug logging for environment variables
if os.getenv("GCP_BUCKET_NAME"):
    print(f"Debug: GCP bucket name is set to: {os.getenv('GCP_BUCKET_NAME')}")
else:
    print("Debug: GCP_BUCKET_NAME is not set")

def upload_to_gcs(video_file, bucket_name: str) -> Optional[tuple[str, str]]:
    """
    Upload a video file to Google Cloud Storage.
    
    Args:
        video_file: The video file from st.file_uploader
        bucket_name: Name of the GCS bucket
        
    Returns:
        tuple: (public_url, gcs_path) of the uploaded file, or None if upload fails
    """
    try:
        # Create storage client
        storage_client = storage.Client()
        
        # Get bucket
        bucket = storage_client.bucket(bucket_name)
        
        # Create a unique filename using timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"uploads/{timestamp}_{video_file.name}"
        blob = bucket.blob(blob_name)
        
        # Create a temporary file to store the video
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(video_file.getvalue())
            tmp_file.flush()
            
            # Upload the file
            blob.upload_from_filename(tmp_file.name)
        
        # Clean up the temporary file
        os.unlink(tmp_file.name)
        
        # Make the blob publicly accessible and get the URL
        blob.make_public()
        gcs_path = f"gs://{bucket_name}/{blob_name}"
        return blob.public_url, gcs_path
        
    except Exception as e:
        st.error(f"Error uploading to GCS: {str(e)}")
        return None

def extract_highlights(gcs_path: str) -> Optional[dict]:
    """
    Extract highlights from the video using Vertex AI Gemini.
    
    Args:
        gcs_path: GCS path to the video (gs://bucket/path/to/video.mp4)
        
    Returns:
        dict: JSON response containing the highlights, or None if extraction fails
    """
    try:
        # Read the prompt template
        with open("prompts/highlight_prompt.md", "r") as f:
            prompt_template = f.read()
        
        # Define the JSON schema for the response
        json_schema = {
            "type": "object",
            "properties": {
                "highlights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "highlight_number": {
                                "type": "integer",
                                "description": "The sequential number of the highlight"
                            },
                            "start_time": {
                                "type": "string",
                                "description": "The timestamp where the highlight begins"
                            },
                            "end_time": {
                                "type": "string",
                                "description": "The timestamp where the highlight ends"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Explanation of why this segment was chosen"
                            },
                            "brief_description": {
                                "type": "string",
                                "description": "Very brief summary of the highlight content"
                            }
                        },
                        "required": ["highlight_number", "start_time", "end_time", "reason", "brief_description"]
                    },
                    "minItems": 3,
                    "maxItems": 5
                }
            },
            "required": ["highlights"]
        }
        
        # Create the prompt with the video file path
        prompt = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt_template
                    },
                    {
                        "file_data": {
                            "mime_type": "video/mp4",
                            "file_uri": gcs_path
                        }
                    }
                ]
            }
        ]
        
        # Generate highlights using Gemini with JSON configuration
        response = gemini_client.generate_content(
            prompt,
            return_json=True,
            json_schema=json_schema
        )
        
        # Ensure we have a valid response
        if not response or not isinstance(response, (str, dict)):
            st.error("Received invalid response from Gemini")
            return None
            
        # Parse the response if it's a string
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                st.error("Failed to parse JSON response")
                return None
        
        # Validate the response has the highlights array
        if not response.get("highlights"):
            st.error("No highlights found in the response")
            return None
            
        return response
        
    except Exception as e:
        st.error(f"Error extracting highlights: {str(e)}")
        return None

def trim_video(input_path: str, start_time: str, end_time: str, output_path: str) -> bool:
    """
    Trim video using ffmpeg.
    
    Args:
        input_path: Path to input video
        start_time: Start timestamp (HH:MM:SS)
        end_time: End timestamp (HH:MM:SS)
        output_path: Path to save trimmed video
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-ss', start_time,
            '-to', end_time,
            '-c', 'copy',  # Use fast copy operation
            output_path,
            '-y'  # Overwrite output file if it exists
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Error trimming video: {e.stderr.decode()}")
        return False
    except Exception as e:
        st.error(f"Error trimming video: {str(e)}")
        return False

def process_highlight_clips(video_file, highlights: dict, bucket_name: str) -> dict:
    """
    Process each highlight by trimming the video and uploading clips to GCS.
    
    Args:
        video_file: Original video file
        highlights: Highlights data
        bucket_name: GCS bucket name
        
    Returns:
        dict: Updated highlights with clip URLs
    """
    # Create temp directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Save original video
        input_path = os.path.join(temp_dir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_file.getvalue())
        
        # Process each highlight
        for highlight in highlights["highlights"]:
            # Create output path for trimmed video
            output_filename = f"highlight_{highlight['highlight_number']}.mp4"
            output_path = os.path.join(temp_dir, output_filename)
            
            # Trim video
            if trim_video(input_path, highlight["start_time"], highlight["end_time"], output_path):
                # Upload trimmed clip to GCS
                storage_client = storage.Client()
                bucket = storage_client.bucket(bucket_name)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                blob_name = f"highlights/{timestamp}_{output_filename}"
                blob = bucket.blob(blob_name)
                
                # Upload the trimmed clip
                blob.upload_from_filename(output_path)
                blob.make_public()
                
                # Add clip URL to highlight data
                highlight["clip_url"] = blob.public_url
            
    return highlights

def display_highlights(highlights: dict, show_clips: bool = True):
    """Display the extracted highlights in a user-friendly format."""
    
    # Create tabs for different views
    tab_all, tab_clips, tab_list = st.tabs(["🎬 All Details", "🎥 Clips Only", "📋 List View"])
    
    # All Details Tab
    with tab_all:
        for highlight in highlights.get("highlights", []):
            with st.container():
                # Create a card-like container with a border
                st.markdown("""
                    <style>
                    .highlight-card {
                        border: 1px solid #e0e0e0;
                        border-radius: 10px;
                        padding: 20px;
                        margin: 10px 0;
                        background-color: #ffffff;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                with st.container():
                    st.markdown('<div class="highlight-card">', unsafe_allow_html=True)
                    
                    # Title with highlight number and description
                    st.markdown(f"### #{highlight['highlight_number']} - {highlight['brief_description']}")
                    
                    # Show video clip if available
                    if show_clips and "clip_url" in highlight:
                        st.video(highlight["clip_url"])
                    
                    # Information columns
                    info_col1, info_col2 = st.columns([1, 2])
                    
                    with info_col1:
                        st.markdown("**⏱️ Time Range**")
                        time_range = f"{highlight['start_time']} - {highlight['end_time']}"
                        st.code(time_range, language=None)
                        
                        # Calculate duration
                        try:
                            start = sum(x * int(t) for x, t in zip([60, 1], highlight['start_time'].split(":")))
                            end = sum(x * int(t) for x, t in zip([60, 1], highlight['end_time'].split(":")))
                            duration = end - start
                            st.caption(f"Duration: {duration} seconds")
                        except:
                            pass
                    
                    with info_col2:
                        st.markdown("**💡 Why This Moment Matters**")
                        st.markdown(f"_{highlight['reason']}_")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
    
    # Clips Only Tab
    with tab_clips:
        for highlight in highlights.get("highlights", []):
            if show_clips and "clip_url" in highlight:
                st.markdown(f"### #{highlight['highlight_number']} - {highlight['brief_description']}")
                st.video(highlight["clip_url"])
                st.markdown("---")
    
    # List View Tab
    with tab_list:
        for highlight in highlights.get("highlights", []):
            with st.expander(f"#{highlight['highlight_number']} - {highlight['brief_description']}"):
                st.markdown(f"**Time Range:** `{highlight['start_time']} - {highlight['end_time']}`")
                st.markdown(f"**Why This Moment:** _{highlight['reason']}_")

def main():
    # Handle health check requests (Cloud Run requirement)
    if os.environ.get("K_SERVICE"):  # We're running in Cloud Run
        if "health" in st.query_params:
            st.json(check_health())
            return
    
    # Custom CSS for better styling
    st.markdown("""
        <style>
        .stApp {
            max-width: 1200px;
            margin: 0 auto;
        }
        .main-title {
            text-align: center;
            margin-bottom: 2rem;
        }
        .stAlert {
            max-width: 800px;
            margin: 0 auto;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Title
    st.markdown("<h1 class='main-title'>🎬 Video Highlights Generator</h1>", unsafe_allow_html=True)
    
    # Check for required environment variables
    if not bucket_name or not project_id:
        st.error("""
            Missing required environment variables. Please ensure the following are set:
            - GCP_BUCKET_NAME: The Google Cloud Storage bucket name
            - GCP_PROJECT: Your Google Cloud project ID
        """)
        return
    
    # Sidebar for video upload
    with st.sidebar:
        st.markdown("### Upload Video")
        st.markdown("Choose a video file to analyze and extract highlights.")
        st.markdown("**Note:** Maximum file size is 200MB")
        video_file = st.file_uploader("", type=["mp4"])
        
        if video_file:
            file_size = len(video_file.getvalue()) / (1024 * 1024)  # Size in MB
            if file_size > 200:
                st.error("File size exceeds 200MB limit!")
                video_file = None
            else:
                st.video(video_file)
                process_button = st.button("Extract Highlights", type="primary")
        else:
            process_button = False
    
    # Main content area
    if video_file and process_button:
        try:
            with st.spinner("Processing your video..."):
                # Upload to GCS
                upload_result = upload_to_gcs(video_file, bucket_name)
                if not upload_result:
                    return
                
                public_url, gcs_path = upload_result
                
                # Extract highlights
                highlights = extract_highlights(gcs_path)
                if not highlights:
                    return
                
                # Process highlight clips
                with st.spinner("Generating highlight clips..."):
                    highlights = process_highlight_clips(video_file, highlights, bucket_name)
                
                # Display results
                display_highlights(highlights)
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            if os.environ.get("K_SERVICE"):  # We're running in Cloud Run
                print(f"Error in Cloud Run: {str(e)}")  # Log to Cloud Run logs
    else:
        # Show welcome message and instructions
        st.markdown("""
            ### Welcome to Video Highlights Generator! 👋
            
            This tool helps you automatically extract and create engaging highlights from your videos.
            
            To get started:
            1. Upload your video using the sidebar (max 200MB)
            2. Click "Extract Highlights"
            3. View your highlights in different formats using the tabs above
            
            The AI will analyze your video and identify the most compelling moments, 
            creating perfectly timed clips that capture the essence of your content.
        """)

if __name__ == "__main__":
    main() 