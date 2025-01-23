#!/bin/bash

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    exit 1
fi

# Read .env file and format variables for Cloud Run
ENV_VARS=$(cat .env | grep -v '^#' | xargs | sed 's/ /,/g')

# Deploy to Cloud Run
gcloud run deploy video-highlights \
    --source . \
    --platform managed \
    --region us-central1 \
    --set-env-vars="$ENV_VARS" \
    --memory=2Gi \
    --cpu=2 \
    --timeout=3600 \
    --allow-unauthenticated 