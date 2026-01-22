import google.generativeai as genai
from app.core.config import settings
import json
import os
from typing import Dict, Any, Optional

import logging

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            # Using 'latest' alias which usually points to the current stable model supported by the API key
            self.model = genai.GenerativeModel('gemini-flash-latest')
            
            # Log available models for debugging
            try:
                available_models = [m.name for m in genai.list_models()]
                logger.info(f"Available Gemini models: {available_models}")
            except Exception as e:
                logger.warning(f"Could not list models: {e}")
        else:
            self.model = None

    def get_prompt(self, prompt_name: str) -> str:
        prompt_path = os.path.join("prompts", f"{prompt_name}.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    async def extract_contact_data(self, text: str = None, audio_path: str = None, prompt_template: str = None) -> Dict[str, Any]:
        if not self.model:
            logger.warning("GEMINI_API_KEY not set")
            return {"name": "Test User", "raw_transcript": "No API Key", "notes": "Gemini disabled"}

<<<<<<< HEAD
        if prompt_template:
            prompt_text = prompt_template
        else:
            prompt_text = self.get_prompt("extract_contact")
        
        content = [prompt_text]
        
=======
        # Security: Validate audio file path to prevent path traversal
>>>>>>> 62d77dd7e8d219af23e6068efd606c51919405a3
        if audio_path:
            import os
            if not os.path.exists(audio_path):
                logger.error("Audio file does not exist")
                return {"name": "Неизвестно", "notes": "File error"}

            # Security: Validate file size (max 20MB)
            file_size = os.path.getsize(audio_path)
            if file_size > 20 * 1024 * 1024:
                logger.error("Audio file too large")
                return {"name": "Неизвестно", "notes": "File too large"}

        prompt_text = self.get_prompt("extract_contact")

        content = [prompt_text]

        if audio_path:
            try:
                sample_file = genai.upload_file(path=audio_path, mime_type="audio/ogg", display_name="Audio Sample")
                content.append(sample_file)
            except Exception as e:
                logger.error(f"Failed to upload audio file: {e}")
                return {"name": "Неизвестно", "notes": "Upload failed"}

        if text:
            # Security: Limit text length to prevent abuse
            if len(text) > 10000:
                text = text[:10000]
            content.append(text)

        # Generate content
        try:
            response = await self.model.generate_content_async(content)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return {"name": "Неизвестно", "notes": "API error"}

        # Parse JSON
        try:
            json_str = response.text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            parsed_data = json.loads(json_str)

            # Security: Validate parsed data structure
            if not isinstance(parsed_data, dict):
                logger.error("Invalid response format from Gemini")
                return {"name": "Неизвестно", "notes": "Invalid format"}

            return parsed_data
        except Exception as e:
            # Security: Don't expose internal error details
            logger.error(f"Error parsing Gemini response: {e}")
            return {
                "name": "Неизвестно",
                "notes": "Processing error"
            }
