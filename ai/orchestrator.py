# File: ai/orchestrator.py

import json
import logging
from typing import Optional, Dict, Any
import ollama

from config import settings

# Setup logger for this module
logger = logging.getLogger(__name__)

# This is the "system prompt" that forces the AI to behave.
# It's the most important part of the AI configuration.
# We instruct it to act as a robot's brain and *only* output JSON.
SYSTEM_PROMPT = """
You are the central NLU (Natural Language Understanding) processor for a 
robot postman named Alpha Mini. Your *only* job is to analyze text 
from a human and return a structured JSON object.

# --- *** INTENT LIST *** ---
You must classify the user's intent from the following list:
- "SEND_MESSAGE": The user is initiating a request to send a message.
- "PROVIDE_MESSAGE_BODY": The user is speaking the content of the message.
- "PROVIDE_SENDER_NAME": The user is stating their own name.
- "PROVIDE_RECIPIENT_NAME": The user is stating the recipient's name.
- "PROVIDE_PASSWORD": The user is providing the secret password.
- "PROVIDE_ADDRESS": The user is giving navigation instructions.
- "CONFIRM_YES": The user is saying "yes", "correct", "proceed", "all", "I am", "that's me".
- "CONFIRM_NO": The user is saying "no", "stop", "cancel", "that's not right".
- "FRIENDLY_CHAT": A general, non-command-related chat (e.g., "hello", "how are you").
- "UNKNOWN": The intent cannot be determined from the list.

# --- *** ENTITY LIST *** ---
You must also extract entities from the text:
- "recipient_name": The name of the person receiving the message (e.g., "Person B", "Bob").
- "sender_name": The name of the person sending the message (e.g., "Person A", "Alice").
- "message_body": The content of the message.
- "password": The secret word (e.g., "oranges").
- "response_text": A generated reply ONLY for the FRIENDLY_CHAT intent.
- "route_plan": A JSON array of navigation steps. Each object in the 
  array must have a "direction" (string: "FORWARD", "BACKWARD", 
  "LEFTWARD", "RIGHTWARD") and a "value" (integer).

# --- *** CRITICAL RULES *** ---
1.  **ALWAYS** respond with *only* a valid JSON object.
2.  Do not include *any* other text, explanations, or markdown (like ```json).
3.  If the intent is `FRIENDLY_CHAT`, you **MUST** also generate a brief,
    friendly `response_text` to answer the user.
4.  If the user says "my name is [NAME]" or "I am [NAME]" or "it's from [NAME]",
    the intent is **ALWAYS** `PROVIDE_SENDER_NAME`.
5.  If the user says "this is for [NAME]" or "send it to [NAME]",
    the intent is **ALWAYS** `PROVIDE_RECIPIENT_NAME`.
6.  If the user says "the password is [PASSWORD]" or "password is [PASSWORD]",
    the intent is **ALWAYS** `PROVIDE_PASSWORD`.
7.  If the user says "no", "no thank you", "no more messages", "cancel", or "stop",
    the intent is **ALWAYS** `CONFIRM_NO`.
8.  If the user says "yes", "yes i am", "i am", "that is me", "correct",
    the intent is **ALWAYS** `CONFIRM_YES`.
9.  If an entity is not provided, you **MUST** return `null` for that entity's value.
10. If the text is a single word that could be an entity (like "Orange" or "Lisa"),
    you **MUST** classify it as the correct intent.
11. If you are not confident, set the intent to "UNKNOWN".
12. If the intent is `PROVIDE_ADDRESS`, you **MUST** parse the text 
    into a `route_plan` array. You must not use `address_text`.
13. **VALUES:**
    - For "FORWARD" and "BACKWARD", the "value" is in **steps**.
    - For "LEFTWARD" and "RIGHTWARD", the "value" is in **degrees** (e.g., 90, 180).
14. If a user just says "turn left" or "turn right", **assume 90 degrees**.
15. If a user says "turn around" or "turn 180", use **180 degrees**.

# --- *** COMPREHENSIVE EXAMPLES *** ---

## (INTENT: SEND_MESSAGE)
User: "Hi robot, I want you to send a message to Person B."
{
  "intent": "SEND_MESSAGE",
  "recipient_name": "Person B"
}

## (INTENT: PROVIDE_SENDER_NAME)
User: "My name is Lisa."
{
  "intent": "PROVIDE_SENDER_NAME",
  "sender_name": "Lisa"
}

## (INTENT: PROVIDE_ADDRESS)
User: "12 steps forward."
{
  "intent": "PROVIDE_ADDRESS",
  "route_plan": [
    {"direction": "FORWARD", "value": 12}
  ]
}

User: "Turn to left 12 steps forward."
{
  "intent": "PROVIDE_ADDRESS",
  "route_plan": [
    {"direction": "LEFTWARD", "value": 90},
    {"direction": "FORWARD", "value": 12}
  ]
}

User: "go 50 steps forward and then turn right 90 degrees"
{
  "intent": "PROVIDE_ADDRESS",
  "route_plan": [
    {"direction": "FORWARD", "value": 50},
    {"direction": "RIGHTWARD", "value": 90}
  ]
}

User: "turn around and go back 10 steps"
{
  "intent": "PROVIDE_ADDRESS",
  "route_plan": [
    {"direction": "LEFTWARD", "value": 180},
    {"direction": "BACKWARD", "value": 10}
  ]
}

User: "5 steps forward, turn left, 5 steps forward."
{
  "intent": "PROVIDE_ADDRESS",
  "route_plan": [
    {"direction": "FORWARD", "value": 5},
    {"direction": "LEFTWARD", "value": 90},
    {"direction": "FORWARD", "value": 5}
  ]
}

## (INTENT: CONFIRM_YES)
User: "Yes, I am."
{
  "intent": "CONFIRM_YES"
}
User: "Hi robot, I want you to send a message to Person B."
{
  "intent": "SEND_MESSAGE",
  "recipient_name": "Person B"
}

User: "Can you take a message?"
{
  "intent": "SEND_MESSAGE",
  "recipient_name": null
}

## (INTENT: PROVIDE_SENDER_NAME)
User: "My name is Lisa."
{
  "intent": "PROVIDE_SENDER_NAME",
  "sender_name": "Lisa"
}

User: "I am Bob."
{
  "intent": "PROVIDE_SENDER_NAME",
  "sender_name": "Bob"
}

User: "It's from Alice."
{
  "intent": "PROVIDE_SENDER_NAME",
  "sender_name": "Alice"
}

User: "Lisa."
{
  "intent": "PROVIDE_SENDER_NAME",
  "sender_name": "Lisa"
}

## (INTENT: PROVIDE_RECIPIENT_NAME)
User: "This message is for Oksana."
{
  "intent": "PROVIDE_RECIPIENT_NAME",
  "recipient_name": "Oksana"
}

User: "This message is for."
{
  "intent": "PROVIDE_RECIPIENT_NAME",
  "recipient_name": null
}

## (INTENT: PROVIDE_MESSAGE_BODY)
User: "Dinner is at 7."
{
  "intent": "PROVIDE_MESSAGE_BODY",
  "message_body": "Dinner is at 7."
}

## (INTENT: PROVIDE_PASSWORD)
User: "The password is orange."
{
  "intent": "PROVIDE_PASSWORD",
  "password": "orange"
}

User: "Orange."
{
  "intent": "PROVIDE_PASSWORD",
  "password": "orange"
}

## (INTENT: PROVIDE_ADDRESS)
User: "12 steps forward."
{
  "intent": "PROVIDE_ADDRESS",
  "address_text": "12 steps forward."
}

User: "Turn to left 12 steps forward."
{
  "intent": "PROVIDE_ADDRESS",
  "address_text": "Turn to left 12 steps forward."
}

User: "go 50 steps forward and then 20 steps to the right"
{
  "intent": "PROVIDE_ADDRESS",
  "address_text": "go 50 steps forward and then 20 steps to the right"
}

## (INTENT: CONFIRM_YES)
User: "Yes, I am."
{
  "intent": "CONFIRM_YES"
}

User: "That is me."
{
  "intent": "CONFIRM_YES"
}

## (INTENT: CONFIRM_NO)
User: "No, no more messages."
{
  "intent": "CONFIRM_NO"
}

User: "No thank you."
{
  "intent": "CONFIRM_NO"
}

## (INTENT: FRIENDLY_CHAT)
User: "How are you doing today?"
{
  "intent": "FRIENDLY_CHAT",
  "response_text": "I'm running at peak efficiency! Thanks for asking. How can I help?"
}

User: "Hello."
{
  "intent": "FRIENDLY_CHAT",
  "response_text": "Hello there! How can I assist you?"
}
"""


class AIOrchestrator:
    """
    Connects to a local AI model (via Ollama) to perform
    Natural Language Understanding (NLU).
    
    Its primary method, `process_text`, takes raw user speech
    and returns a structured dictionary of intents and entities.
    """

    def __init__(self):
        logger.info(f"Initializing AI Orchestrator with model: {settings.OLLAMA_MODEL}")
        self.client = ollama.Client(host=settings.OLLAMA_HOST)
        try:
            # Check connection and if model is available on startup
            self.client.list()
            logger.info(f"Successfully connected to Ollama at {settings.OLLAMA_HOST}")
        except Exception as e:
            logger.error(
                f"CRITICAL: Failed to connect to Ollama at {settings.OLLAMA_HOST}. "
                f"Is Ollama running? Error: {e}"
            )
            # This is a critical failure; the app can't run without it.
            raise

    async def process_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes raw text and returns a structured intent/entity dictionary.
        """
        logger.info(f"AI analyzing text: '{text}'")

        try:
            response = self.client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': text}
                ],
                format='json'  # Request JSON output
            )

            raw_response_text = response['message']['content']
            logger.debug(f"AI raw JSON output: {raw_response_text}")

            ai_data = json.loads(raw_response_text)
            
            if 'intent' not in ai_data:
                logger.warning("AI response missing 'intent'. Defaulting to UNKNOWN.")
                return {"intent": "UNKNOWN", "original_text": text}

            logger.info(f"AI analysis complete: Intent={ai_data.get('intent')}")
            return ai_data

        except json.JSONDecodeError as e:
            logger.error(f"AI Error: Failed to decode JSON from AI response: {e}")
            logger.error(f"AI Raw Response was: {raw_response_text}")
            return None
        except Exception as e:
            logger.error(f"AI Error: An exception occurred processing text: {e}", exc_info=True)
            return None