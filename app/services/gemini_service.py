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
            # Fallback for dev/testing if no key? Or raise error.
            print("Warning: GEMINI_API_KEY not set") 
            return {"name": "Test User", "raw_transcript": "No API Key", "notes": "Gemini disabled"}

        if prompt_template:
            prompt_text = prompt_template
        else:
            prompt_text = self.get_prompt("extract_contact")
        
        content = [prompt_text]
        
        if audio_path:
            # Upload file. Note: This is synchronous in current SDK usually, or awaitable?
            # genai.upload_file returns a File object.
            # It performs network request. Ideally we should run this in thread pool if it's blocking.
            # But specific SDK behavior might vary. upload_file seems synchronous.
            sample_file = genai.upload_file(path=audio_path, mime_type="audio/ogg", display_name="Audio Sample")
            content.append(sample_file)
        
        if text:
            content.append(text)

        # Generate content
        # model.generate_content_async is preferred for async
        response = await self.model.generate_content_async(content)
        
        # Parse JSON
        try:
            json_str = response.text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            
            return json.loads(json_str)
        except Exception as e:
            print(f"Error parsing Gemini response: {e}")
            return {
                "name": "Неизвестно",
                "raw_transcript": response.text if response.text else "Error",
                "notes": f"Processing error: {str(e)}"
            }
