import google.generativeai as genai
from app.core.config import settings
import json
import os
from typing import Dict, Any, Optional

class GeminiService:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def get_prompt(self, prompt_name: str) -> str:
        prompt_path = os.path.join("prompts", f"{prompt_name}.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    async def extract_contact_data(self, text: str = None, audio_path: str = None) -> Dict[str, Any]:
        if not self.model:
            # Fallback for dev/testing if no key? Or raise error.
            print("Warning: GEMINI_API_KEY not set") 
            return {"name": "Test User", "raw_transcript": "No API Key", "notes": "Gemini disabled"}

        prompt_text = self.get_prompt("extract_contact")
        
        content = [prompt_text]
        
        if audio_path:
            # Upload file. Note: This is synchronous in current SDK usually, or awaitable?
            # genai.upload_file returns a File object.
            # It performs network request. Ideally we should run this in thread pool if it's blocking.
            # But specific SDK behavior might vary. upload_file seems synchronous.
            sample_file = genai.upload_file(path=audio_path, display_name="Audio Sample")
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
