import google.generativeai as genai
from openai import AsyncOpenAI
from app.core.config import settings
import asyncio
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, gemini_api_key: str = None, openai_api_key: str = None):
        self.provider = None
        self.gemini_model = None
        self.openai_client = None

        g_key = gemini_api_key or settings.GEMINI_API_KEY
        o_key = openai_api_key or settings.OPENAI_API_KEY

        # Try Gemini first
        if g_key:
            try:
                genai.configure(api_key=g_key)
                # Using 'gemini-1.5-flash' or similar recent model.
                # Original code used 'gemini-flash-latest'
                self.gemini_model = genai.GenerativeModel('gemini-flash-latest')
                self.provider = "gemini"
                logger.info("AIService initialized with Gemini")
            except Exception as e:
                logger.error(f"Failed to configure Gemini: {e}")
                self.gemini_model = None

        # If Gemini not available, try OpenAI
        if not self.provider and o_key:
            try:
                self.openai_client = AsyncOpenAI(api_key=o_key)
                self.provider = "openai"
                logger.info("AIService initialized with OpenAI")
            except Exception as e:
                logger.error(f"Failed to configure OpenAI: {e}")
                self.openai_client = None
        
        if not self.provider:
            logger.warning("No AI provider available (GEMINI_API_KEY and OPENAI_API_KEY are missing or invalid)")

    def get_prompt(self, prompt_name: str) -> str:
        prompt_path = os.path.join("prompts", f"{prompt_name}.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    async def extract_contact_data(self, text: str = None, audio_path: str = None, prompt_template: str = None) -> Dict[str, Any]:
        if not self.provider:
            logger.warning("No AI provider set")
            return {"name": "Test User", "raw_transcript": "No API Key", "notes": "AI disabled"}

        if prompt_template:
            prompt_text = prompt_template
        else:
            prompt_text = self.get_prompt("extract_contact")
        
        # Prepare context with current time
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_str = f"Current Date/Time: {current_time_str}\n\n"
        full_system_prompt = f"{context_str}{prompt_text}"

        if self.provider == "gemini":
            return await self._extract_gemini(text, audio_path, full_system_prompt)
        elif self.provider == "openai":
            return await self._extract_openai(text, audio_path, full_system_prompt)
        
        return {"name": "Error", "notes": "Unknown provider"}

    async def _extract_gemini(self, text: str, audio_path: str, prompt: str) -> Dict[str, Any]:
        content = [prompt] # System prompt as first part of content

        # Size check logic from original code
        if audio_path:
            if not os.path.exists(audio_path):
                logger.error("Audio file does not exist")
                return {"name": "Неизвестно", "notes": "File error"}

            file_size = os.path.getsize(audio_path)
            if file_size > 20 * 1024 * 1024:
                return {"name": "Неизвестно", "notes": "File too large"}

            try:
                # Use asyncio.to_thread for sync upload
                sample_file = await asyncio.to_thread(genai.upload_file, path=audio_path, mime_type="audio/ogg")
                content.append(sample_file)
            except Exception as e:
                logger.exception(f"Failed to upload audio file to Gemini: {e}")
                return {"name": "Неизвестно", "notes": f"Upload failed: {str(e)}"}

        if text:
            if len(text) > 10000:
                text = text[:10000]
            content.append(text)

        try:
            logger.info(f"Calling Gemini API")
            response = await asyncio.to_thread(
                self.gemini_model.generate_content,
                content,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                )
            )
            return self._parse_json_response(response.text)
        except Exception as e:
            logger.exception(f"Gemini API error: {e}")
            return {"name": "Неизвестно", "notes": f"API error: {str(e)}", "error": str(e)}

    async def _extract_openai(self, text: str, audio_path: str, system_prompt: str) -> Dict[str, Any]:
        user_content_parts = []
        transcript = None

        if audio_path:
            if os.path.exists(audio_path):
                try:
                    logger.info(f"Transcribing audio with OpenAI Whisper: {audio_path}")
                    with open(audio_path, "rb") as audio_file:
                        transcription = await self.openai_client.audio.transcriptions.create(
                            model="whisper-1", 
                            file=audio_file
                        )
                        transcript = transcription.text
                        logger.info("Transcription successful")
                        user_content_parts.append(f"Audio Transcript:\n{transcript}")
                except Exception as e:
                    logger.error(f"OpenAI Whisper error: {e}")
                    user_content_parts.append(f"[Audio Processing Failed: {str(e)}]")
            else:
                 user_content_parts.append("[Audio File Missing]")

        if text:
            user_content_parts.append(f"Text Input:\n{text}")

        user_message = "\n\n".join(user_content_parts)
        if not user_message:
            user_message = "No input provided."

        try:
            logger.info("Calling OpenAI GPT-4o")
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return self._parse_json_response(content)
        except Exception as e:
            logger.exception(f"OpenAI API error: {e}")
            return {"name": "Неизвестно", "notes": f"API error: {str(e)}", "error": str(e)}

    def _parse_json_response(self, json_str: str) -> Dict[str, Any]:
        try:
            json_str = json_str.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            
            parsed = json.loads(json_str)
            if not isinstance(parsed, dict):
                return {"name": "Неизвестно", "notes": "Invalid format"}
            return parsed
        except Exception as e:
            logger.error(f"JSON parsing error: {e}")
            return {"name": "Неизвестно", "notes": "JSON parsing error"}

    async def customize_card_intro(self, user_profile: str, target_contact: str) -> Dict[str, str]:
        if not self.provider:
             return {"message": "Привет! Буду рад оставаться на связи.", "strategy": ""}

        prompt_content = f"""
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
            if self.provider == "gemini":
                response = await self.gemini_model.generate_content_async(
                     prompt_content,
                     generation_config=genai.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                text_response = response.text
            elif self.provider == "openai":
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a helpful networking assistant."},
                        {"role": "user", "content": prompt_content}
                    ],
                    response_format={"type": "json_object"}
                )
                text_response = response.choices[0].message.content
            
            return self._parse_json_response(text_response)

        except Exception as e:
             return {"message": "Привет! Буду рад оставаться на связи.", "strategy": "Ошибка генерации совета."}

    async def generate_json(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Generates structured JSON data from the AI provider.
        """
        if not self.provider:
            return {"error": "No AI provider configured"}
        
        try:
            if self.provider == "gemini":
                # Gemini often works better with combined prompt for simple tasks, or using system instructions if configured.
                # Here we combine them as done in previous valid logic.
                full_content = f"{system_prompt}\n\nInput Data:\n{user_input}"
                response = await asyncio.to_thread(
                    self.gemini_model.generate_content,
                    full_content,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                return self._parse_json_response(response.text)
            
            elif self.provider == "openai":
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input}
                    ],
                    response_format={"type": "json_object"}
                )
                return self._parse_json_response(response.choices[0].message.content)
                
        except Exception as e:
            logger.error(f"AI generate_json error: {e}")
            return {"error": str(e)}
