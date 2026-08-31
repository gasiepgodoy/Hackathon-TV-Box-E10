#!/bin/bash
# Startup script for edge-tts FastAPI server on Linux (Orange Pi PC)
echo "Starting Edge-TTS API Server on port 8000..."
python3 -m uvicorn tts_api.main:app --host 0.0.0.0 --port 8000
