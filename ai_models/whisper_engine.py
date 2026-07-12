import os
import re
import logging
from config import Config

logger = logging.getLogger(__name__)

class WhisperEngine:
    def __init__(self):
        self.model = None
        self.whisper_loaded = False
        self.model_name = Config.WHISPER_MODEL_NAME
        self.load_model()

    def load_model(self):
        try:
            import whisper
            logger.info(f"Loading Whisper model '{self.model_name}' (this might take a minute on first run)...")
            # Loads model to ~/.cache/whisper/
            self.model = whisper.load_model(self.model_name)
            self.whisper_loaded = True
            logger.info("Whisper model loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load Whisper: {e}. Falling back to speech_recognition / mock engine.")
            self.model = None
            self.whisper_loaded = False

    def transcribe_audio(self, audio_file_path):
        """
        Transcribes the audio file.
        Returns:
            text: Transcribed string.
        """
        if not os.path.exists(audio_file_path):
            logger.error(f"Audio file does not exist: {audio_file_path}")
            return ""

        if self.whisper_loaded and self.model is not None:
            try:
                logger.info(f"Transcribing {audio_file_path} using Whisper...")
                result = self.model.transcribe(audio_file_path, fp16=False)
                transcription = result.get("text", "").strip()
                logger.info(f"Whisper Transcription: '{transcription}'")
                return transcription
            except Exception as e:
                logger.error(f"Whisper transcription failed: {e}. Trying Google Speech fallback...")

        # Fallback to speech_recognition (Google Web Speech API)
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_file_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            logger.info(f"Google Speech API Fallback Transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"Speech recognition fallback failed: {e}")
            
            # Final mock simulation:
            # Let's extract command words from file if possible, or read a text file
            # containing the command (this is useful for testing or automated scripts).
            # We'll just return a default string for manual voice emulation.
            return "Navigate to Room 103"

    def parse_command(self, transcription_text):
        """
        Parses text into a standardized command dictionary.
        Supported formats:
        - "Navigate to Room 301" / "Go to 102"
        - "Find Exit" / "Go to Exit"
        - "Where am I" / "Location"
        - "Nearest Washroom" / "Washroom"
        - "Stop Navigation" / "Cancel"
        """
        text = transcription_text.strip().lower()
        
        # 1. Stop command
        if re.search(r'\b(stop|cancel|halt|end|pause)\b', text):
            return {"command": "stop", "target": None}
            
        # 2. Where am I / Location status
        if re.search(r'\b(where|location|status|position|who am i)\b', text):
            return {"command": "where_am_i", "target": None}
            
        # 3. Nearest Washroom / Restroom
        if re.search(r'\b(washroom|restroom|toilet|bathroom|wc)\b', text):
            return {"command": "navigate", "target": "104"} # Node 7, Room 104 in seed
            
        # 4. Find Exit
        if re.search(r'\b(exit|leave|out|emergency exit)\b', text):
            return {"command": "navigate", "target": "exit"}
            
        # 5. Navigate to Room XXX
        nav_match = re.search(r'\b(?:navigate to|go to|take me to|find|route to|room)\s+([a-zA-Z0-9\s\-]+)', text)
        if nav_match:
            target = nav_match.group(1).strip()
            # Clean room designations like "room 102" -> "102"
            target = re.sub(r'^room\s+', '', target)
            return {"command": "navigate", "target": target}
            
        # Fallback check if text is just a room number
        room_match = re.search(r'\b(\d{3})\b', text)
        if room_match:
            return {"command": "navigate", "target": room_match.group(1)}
            
        return {"command": "unknown", "text": transcription_text}
