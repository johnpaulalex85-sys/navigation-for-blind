# AIDEN Installation Guide

This guide walks you through setting up the **AIDEN Indoor Navigation Assistant** on a local development machine.

---

## Prerequisites

Ensure you have the following installed:
1. **Python 3.10+** (Python 3.13 was tested successfully)
2. **Node.js & npm** (optional, only if modifying visual assets)
3. **ffmpeg** (optional, recommended for local offline Whisper voice command compilation)

---

## Step 1: Clone and Navigate to the Directory
Open your terminal (PowerShell, Command Prompt, or Bash) and navigate to the project directory:
```bash
cd "D:\main project\Building navigation\AIDEN"
```

## Step 2: Create a Python Virtual Environment
Creating a virtual environment ensures dependencies do not conflict with your global python installation.
```bash
python -m venv venv
```

Activate the environment:
* **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
* **Windows (Command Prompt)**:
  ```cmd
  .\venv\Scripts\activate.bat
  ```
* **macOS / Linux**:
  ```bash
  source venv/bin/activate
  ```

## Step 3: Install Optimized PyTorch (CPU-Only)
Whisper and EasyOCR rely on PyTorch. Standard PyTorch installations bundle massive CUDA GPU binary files (up to 2.5GB). To install the lightweight CPU-only version (approx 150MB):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

## Step 4: Install Required Packages
Install the remaining packages listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```

## Step 5: Initialize the Database
Initializes the SQLite schema and seeds the default graph (Engineering Block nodes and edges):
```bash
python -m database.db_helper
```
You should see: `Database initialized and seeded.`

## Step 6: Start the AIDEN Flask Server
```bash
python app.py
```

Open your browser and navigate to:
[http://localhost:5000](http://localhost:5000)

---

## Troubleshooting

### EasyOCR Downloading Models
On your first run, EasyOCR will download its English character detection model parameters into your user directory `~/.EasyOCR/`. This happens automatically and may take a moment.

### Whisper Downloading Weights
Whisper will download the default `tiny` model parameters (approx 75MB) to `~/.cache/whisper/` on the first voice command call. 

### Audio Transcription Errors (FFmpeg)
If Whisper fails to parse audio recordings, ensure `ffmpeg` is installed on your OS PATH. Alternatively, AIDEN contains a built-in fallback that automatically channels voice commands through the Google Web Speech API, allowing voice control to work out of the box without local model configuration.
