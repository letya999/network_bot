import google.generativeai as genai
from app.core.config import settings
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import importlib.metadata
import logging

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                # Using 'latest' alias which usually points to the current stable model
                self.model = genai.GenerativeModel('gemini-flash-latest')
            except Exception as e:
                logger.error(f"Failed to configure Gemini: {e}")
                self.model = None
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

        if prompt_template:
            prompt_text = prompt_template
        else:
            prompt_text = self.get_prompt("extract_contact")
        
        # Prepare context with current time
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_str = f"Current Date/Time: {current_time_str}\n\n"
        
        # We need to prepend this to the prompt text OR add it as a separate text part.
        # Adding to prompt text is safer as it acts as system instruction.
        full_prompt_text = f"{context_str}{prompt_text}"
        
        content = [full_prompt_text]
        
        # Security: Validate audio file path
        if audio_path:
            if not os.path.exists(audio_path):
                logger.error("Audio file does not exist")
                return {"name": "Неизвестно", "notes": "File error"}

            file_size = os.path.getsize(audio_path)
            if file_size > 20 * 1024 * 1024:
                logger.error("Audio file too large")
                return {"name": "Неизвестно", "notes": "File too large"}

            try:
                logger.info(f"Uploading audio file: {audio_path} (size: {file_size} bytes)")
                sample_file = genai.upload_file(path=audio_path, mime_type="audio/ogg")
                logger.info(f"Upload successful. File: {sample_file.name}")
                content.append(sample_file)
            except Exception as e:
                logger.exception(f"Failed to upload audio file: {e}")
                return {"name": "Неизвестно", "notes": f"Upload failed: {str(e)}"}

        if text:
            if len(text) > 10000:
                text = text[:10000]
            content.append(text)

        # Generate content
        try:
            logger.info(f"Calling Gemini API with {len(content)} content items")
            response = await self.model.generate_content_async(
                content,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            logger.info("Gemini API call successful")
        except Exception as e:
            logger.exception(f"Gemini API error: {e}")
            return {"name": "Неизвестно", "notes": f"API error: {str(e)}", "error": str(e)}

        # Parse JSON
        try:
            json_str = response.text.strip()
            logger.info(f"Raw response (first 200 chars): {json_str[:200]}")
            
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            parsed_data = json.loads(json_str)
            logger.info(f"Successfully parsed JSON: {list(parsed_data.keys())}")

            if not isinstance(parsed_data, dict):
                logger.error("Invalid response format from Gemini")
                return {"name": "Неизвестно", "notes": "Invalid format"}

            return parsed_data
        except Exception as e:
            logger.exception(f"Error parsing Gemini response: {e}")
            return {
                "name": "Неизвестно",
                "notes": f"Processing error: {str(e)}",
                "error": str(e)
            }

    async def customize_card_intro(self, user_profile: str, target_contact: str) -> Dict[str, str]:
        if not self.model:
            return {"message": "Привет! Буду рад оставаться на связи.", "strategy": ""}
            
        prompt = f"""
        Act as a professional networking coach and copywriter.
        
        My Profile (Sender):
        {user_profile}
        
        Target Contact (Recipient):
        {target_contact}
        
        Task 1: Networking Message
        Write a short, direct, and conversational message in Russian.
        - Address the person by FIRST NAME ONLY.
        - Analyze our roles/seniority levels. 
          * If I am senior (e.g., C-level, Head) and they are junior/mid (e.g., Analyst), be supportive/mentor-like but professional.
          * If we are peers, be collaborative/casual.
          * If I am selling/seeking partnership, be value-focused.
        - Mention a specific synergy or why I'm connecting.
        - Length: Short (2-3 sentences).
        - No emojis. No subjects lines. No lists.
        
        Task 2: Strategy Advice
        Based on our profiles and the message tone, suggest SPECIFIC follow-up actions.
        - Recommend EXACTLY which materials to send next (e.g., "Send your Portfolio link", "Attach the Pitch Deck", "Link to specific case study on website").
        - Explain WHY this material fits the recipient's role/interest.
        - e.g., "Since they are a technical lead, send your GitHub or technical documentation link."
        
        Output JSON:
        {{
            "message": "The text message string",
            "strategy": "Your specific advice on what materials/links to send next and why."
        }}
        """
        
        try:
             response = await self.model.generate_content_async(
                 prompt,
                 generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                )
             )
             
             text = response.text.strip()
             # Cleanup code blocks if present (though mime_type json usually avoids this, sometimes it adds it)
             if text.startswith("```json"): text = text[7:]
             if text.startswith("```"): text = text[3:]
             if text.endswith("```"): text = text[:-3]
             
             return json.loads(text)
        except Exception as e:
             logger.error(f"Gemini custom intro error: {e}")
             return {"message": "Привет! Буду рад оставаться на связи.", "strategy": "Ошибка генерации совета."}
