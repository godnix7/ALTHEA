"""
Mental Health Agent - Integrates with Ollama for generating AI responses
"""
import requests
import json
import os
from typing import Optional, List, Dict


class MHAgent:
    """Mental Health Agent that uses Ollama for generating empathetic responses"""
    
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the MH Agent
        
        Args:
            base_url: Base URL for Ollama API (default: from OLLAMA_BASE_URL env var or http://localhost:11434)
            model: Model name to use (default: from OLLAMA_MODEL env var or llama2)
        """
        self.base_url = (base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')).rstrip('/')
        self.model = model or os.getenv('OLLAMA_MODEL', 'llama3:latest')
        self.api_url = f"{self.base_url}/api/generate"
        
        print(f"[AGENT] Initialized with base_url={self.base_url}, model={self.model}")
        
        # Try to detect available model if default doesn't work
        self._verify_model()
    
    def _verify_model(self):
        """Verify the model is available, try to find an alternative if not"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                # Check if our model exists
                if not any(self.model in name for name in model_names):
                    # Try to find llama3, llama2, or mistral
                    for preferred in ['llama3', 'llama2', 'mistral']:
                        for name in model_names:
                            if preferred in name.lower():
                                print(f"Model {self.model} not found, using {name} instead")
                                self.model = name
                                return
                    if model_names:
                        print(f"Model {self.model} not found, using {model_names[0]} instead")
                        self.model = model_names[0]
        except Exception as e:
            print(f"Could not verify model availability: {e}")
    
    def _build_system_prompt(self, gad9_level: Optional[str] = None) -> str:
        """Build system prompt for mental health support"""
        base_prompt = """You are Althea, a compassionate mental health support assistant. Your role is to:
- Provide empathetic, non-judgmental support
- Offer practical coping strategies when appropriate
- Recognize when professional help might be needed
- Use warm, understanding language
- Keep responses concise but meaningful (2-4 sentences)
- Avoid giving medical diagnoses or advice
- Advice some movies according to the user's mood  

Remember: You're here to listen and support, not to replace professional mental health care."""
        
        if gad9_level and gad9_level in ('Moderate', 'Severe'):
            base_prompt += f"\n\nNote: The user's recent GAD-9 assessment showed {gad9_level} anxiety levels. Be especially supportive and consider suggesting grounding techniques or professional support when appropriate."
        
        return base_prompt
    
    def _build_conversation_context(self, recent_messages: List[Dict]) -> str:
        """Build conversation context from recent messages"""
        if not recent_messages:
            return ""
        
        context = "Recent conversation:\n"
        for msg in recent_messages[-6:]:  # Last 6 messages for context
            role = "User" if msg.get('sender') == 'user' else "Althea"
            context += f"{role}: {msg.get('message', '')}\n"
        return context
    
    def generate_response(
        self, 
        user_message: str, 
        gad9_level: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        provider: str = 'ollama',
        api_keys: Optional[Dict[str, str]] = None
    ) -> Dict[str, Optional[str]]:
        """
        Generate a response using the selected provider
        """
        api_keys = api_keys or {}
        
        if provider == 'openai' and api_keys.get('openai'):
            return self._generate_openai(user_message, gad9_level, conversation_history, api_keys['openai'])
        elif provider == 'gemini' and api_keys.get('gemini'):
            return self._generate_gemini(user_message, gad9_level, conversation_history, api_keys['gemini'])
        elif provider == 'anthropic' and api_keys.get('anthropic'):
            return self._generate_anthropic(user_message, gad9_level, conversation_history, api_keys['anthropic'])
        else:
            # Default to Ollama
            return self._generate_ollama(user_message, gad9_level, conversation_history)

    def _generate_ollama(
        self, 
        user_message: str, 
        gad9_level: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Optional[str]]:
        try:
            system_prompt = self._build_system_prompt(gad9_level)
            context = self._build_conversation_context(conversation_history or [])
            full_prompt = f"{system_prompt}\n\n{context}\n\nUser: {user_message}\nAlthea:"
            
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.7}
            }
            
            response = requests.post(self.api_url, json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                generated_text = result.get('response', '').strip()
                return {'text': generated_text, 'provider': 'ollama', 'error': None}
            return self._fallback_response(user_message, gad9_level, reason=f"Ollama error {response.status_code}")
        except Exception as e:
            return self._fallback_response(user_message, gad9_level, reason=str(e))

    def _generate_openai(self, user_message, gad9_level, history, api_key):
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            messages = [{"role": "system", "content": self._build_system_prompt(gad9_level)}]
            for msg in (history or [])[-5:]:
                role = "user" if msg.get('sender') == 'user' else "assistant"
                messages.append({"role": role, "content": msg.get('message', '')})
            messages.append({"role": "user", "content": user_message})
            
            payload = {"model": "gpt-4o-mini", "messages": messages, "temperature": 0.7}
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                text = response.json()['choices'][0]['message']['content'].strip()
                return {'text': text, 'provider': 'openai', 'error': None}
            return self._fallback_response(user_message, gad9_level, reason=f"OpenAI error {response.status_code}")
        except Exception as e:
            return self._fallback_response(user_message, gad9_level, reason=str(e))

    def _generate_gemini(self, user_message, gad9_level, history, api_key):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            system_instruction = self._build_system_prompt(gad9_level)
            
            contents = []
            for msg in (history or [])[-5:]:
                role = "user" if msg.get('sender') == 'user' else "model"
                contents.append({"role": role, "parts": [{"text": msg.get('message', '')}]})
            contents.append({"role": "user", "parts": [{"text": user_message}]})

            payload = {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7}
            }
            
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                return {'text': text, 'provider': 'gemini', 'error': None}
            return self._fallback_response(user_message, gad9_level, reason=f"Gemini error {response.status_code}")
        except Exception as e:
            return self._fallback_response(user_message, gad9_level, reason=str(e))

    def _generate_anthropic(self, user_message, gad9_level, history, api_key):
        try:
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            system_prompt = self._build_system_prompt(gad9_level)
            messages = []
            for msg in (history or [])[-5:]:
                role = "user" if msg.get('sender') == 'user' else "assistant"
                messages.append({"role": role, "content": msg.get('message', '')})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": messages,
                "temperature": 0.7
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                text = response.json()['content'][0]['text'].strip()
                return {'text': text, 'provider': 'anthropic', 'error': None}
            return self._fallback_response(user_message, gad9_level, reason=f"Anthropic error {response.status_code}")
        except Exception as e:
            return self._fallback_response(user_message, gad9_level, reason=str(e))

    
    def _fallback_response(
        self,
        user_message: str,
        gad9_level: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """Fallback response when Ollama is unavailable"""
        lowered = user_message.lower()
        response_text = ""
        
        if any(keyword in lowered for keyword in ['anxious', 'anxiety', 'stress', 'stressed']):
            if gad9_level and gad9_level in ('Moderate', 'Severe'):
                response_text = (
                    "I remember your recent GAD-9 check showed increased anxiety. "
                    "Would you like to try a grounding exercise or plan a support call?"
                )
            else:
                response_text = "It sounds like things are feeling heavy. Would you like to try a short breathing exercise together?"
        
        if any(keyword in lowered for keyword in ['happy', 'good', 'great']):
            response_text = "That's wonderful to hear! Would you like to save this moment or explore a quick gratitude practice?"
        
        if any(keyword in lowered for keyword in ['sleep', 'tired', 'insomnia']):
            response_text = "Sleep can be tricky. I can walk you through a simple wind-down routine if you'd like."
        
        if gad9_level and gad9_level in ('Moderate', 'Severe'):
            response_text = (
                "Thanks for sharing — I'm here with you. Based on your recent GAD-9 result, "
                "would you like coping ideas or help finding professional support?"
            )
        if not response_text:
            response_text = "Thanks for sharing — I hear you. Would you like a breathing exercise or a quick grounding technique?"

        return {
            'text': response_text,
            'provider': 'fallback',
            'error': reason,
        }


# Global agent instance
_agent_instance: Optional[MHAgent] = None


def get_agent() -> MHAgent:
    """Get or create the global agent instance"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = MHAgent()
    return _agent_instance


def set_agent(agent: MHAgent):
    """Set a custom agent instance (useful for testing)"""
    global _agent_instance
    _agent_instance = agent

