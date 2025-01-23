# 🎬 Video Highlights Generator

An AI-powered application that automatically extracts engaging highlights from videos using Google Cloud's Vertex AI Gemini and Streamlit. The app analyzes videos to identify compelling moments, creates highlight clips, and presents them in an intuitive interface.

## ✨ Features

- 🎥 Upload and process MP4 videos (up to 200MB)
- 🤖 AI-powered video analysis using Vertex AI Gemini
- ✂️ Automatic highlight clip generation
- 🎯 Smart detection of key moments and story arcs
- 📊 Multiple views for highlights (detailed, clips-only, list view)
- ☁️ Cloud-ready with Google Cloud Storage integration

## 🚀 Getting Started

### Prerequisites

- Python 3.9 or higher
- FFmpeg installed on your system
- Google Cloud Project with:
  - Vertex AI API enabled
  - Cloud Storage bucket created
  - Appropriate service account permissions

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/video-highlights-generator.git
cd video-highlights-generator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment variables:
```bash
cp .env.example .env
```

Edit `.env` with your Google Cloud settings:
```
GCP_PROJECT=your-project-id
GCP_BUCKET_NAME=your-bucket-name
```

### Local Development

Run the Streamlit app locally:
```bash
streamlit run app.py
```

The app will be available at `http://localhost:8501`

## 🌩️ Cloud Run Deployment

### Option 1: Deploy from Source

1. Make the deployment script executable:
```bash
chmod +x deploy.sh
```

2. Deploy to Cloud Run:
```bash
./deploy.sh
```

### Option 2: Manual Deployment

Deploy using the Google Cloud Console or gcloud command:

```bash
gcloud run deploy video-highlights \
    --source . \
    --platform managed \
    --region REGION \
    --set-env-vars="GCP_PROJECT=your-project-id,GCP_BUCKET_NAME=your-bucket-name" \
    --memory=2Gi \
    --cpu=2 \
    --timeout=3600 \
    --allow-unauthenticated
```

## 🎯 Usage

1. Access the application through your browser
2. Upload a video file (MP4 format, max 200MB)
3. Click "Extract Highlights"
4. View the generated highlights in three different formats:
   - 🎬 All Details: Complete information with video clips
   - 🎥 Clips Only: Just the highlight videos
   - 📋 List View: Compact text-based overview

## 🛠️ Technical Details

The application uses:
- Streamlit for the web interface
- Vertex AI Gemini for video analysis
- FFmpeg for video processing
- Google Cloud Storage for file storage
- Python's tempfile for secure file handling

### Architecture

1. **Upload**: Video is uploaded through Streamlit's interface
2. **Storage**: File is stored in Google Cloud Storage
3. **Analysis**: Vertex AI Gemini analyzes the video
4. **Processing**: FFmpeg creates highlight clips
5. **Display**: Results are shown in a tabbed interface

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🔒 Security

- All file operations use secure temporary files
- Cloud storage access is managed through GCP IAM
- File size limits prevent abuse
- Environment variables for sensitive configuration

## ⚠️ Limitations

- Maximum video file size: 200MB
- Supported format: MP4 only
- Processing time varies with video length
- Requires Google Cloud Platform services

## 📧 Support

For support, please open an issue in the GitHub repository. 