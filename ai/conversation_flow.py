# File: ai/conversation_flow.py

import asyncio
import logging
from enum import Enum, auto
from typing import Optional, Dict, Any, TYPE_CHECKING

from config import prompts

# Avoid circular imports for type hinting
if TYPE_CHECKING:
    from core.state_manager import StateManager

logger = logging.getLogger(__name__)

# --- *** NEW: Stop words to validate against *** ---
INVALID_NAMES = ["this", "for", "a", "an", "the", "is", "to", "message"]


# This defines the internal state of the conversation
class ConversationStep(Enum):
    IDLE = auto()                    # Doing nothing
    AWAITING_MESSAGE_BODY = auto()   # Just got "send message" intent
    AWAITING_SENDER_NAME = auto()    # Got message, asking who it's from
    AWAITING_RECIPIENT_NAME = auto() # Got sender, asking who it's for
    AWAITING_PROTECTION = auto()     # Got recipient, asking about password
    AWAITING_PASSWORD = auto()       # User said "yes" to protection
    AWAITING_ADDRESS = auto()        # Got protection info, asking for address
    READY_TO_SEND = auto()           # All info collected, job is complete


class ConversationFlow:
    """
    Manages the stateful, multi-step conversation for composing a message.
    
    This class is instantiated by the AIOrchestrator or main loop and
    is used to handle a single "send message" job.
    """

    def __init__(self, state_manager: 'StateManager'):
        self.state_manager = state_manager
        self.current_step = ConversationStep.IDLE
        
        # This dictionary will store the message as it's built
        self.message_job: Dict[str, Any] = {}
        
        # This will be the final packaged job
        self.completed_job: Optional[Dict[str, Any]] = None

    def start_new_message_flow(self, initial_ai_data: Dict[str, Any]):
        """
        Kicks off the conversation from a "SEND_MESSAGE" intent.
        """
        logger.info("Starting new message composition flow")
        self.current_step = ConversationStep.IDLE
        self.completed_job = None
        self.message_job = {
            "sender_name": initial_ai_data.get("sender_name"),
            "recipient_name": initial_ai_data.get("recipient_name"),
            "message_body": initial_ai_data.get("message_body"),
            "password": None,
            "address_text": None,
        }
        
        # Start the first step
        self.current_step = ConversationStep.AWAITING_MESSAGE_BODY
        # We use a task so this can run without blocking the main loop
        asyncio.create_task(self.state_manager.safe_say(prompts.PROMPT_FOR_MESSAGE))

    async def handle_ai_response(self, ai_data: Dict[str, Any]):
        """
        The main state machine. This is called by the main loop
        every time the user says something *during* a conversation.
        """
        intent = ai_data.get("intent")
        
        # --- 1. Awaiting Message Body ---
        if self.current_step == ConversationStep.AWAITING_MESSAGE_BODY:
            if intent == "PROVIDE_MESSAGE_BODY":
                self.message_job["message_body"] = ai_data.get("message_body")
                logger.info(f"Got message body: {self.message_job['message_body']}")
                self.current_step = ConversationStep.AWAITING_SENDER_NAME
                await self.state_manager.safe_say(prompts.PROMPT_FOR_SENDER_NAME)
            else:
                await self.state_manager.safe_say("I'm sorry, I didn't get that. " + prompts.PROMPT_FOR_MESSAGE)

        # --- 2. Awaiting Sender Name ---
        elif self.current_step == ConversationStep.AWAITING_SENDER_NAME:
            if intent == "PROVIDE_SENDER_NAME":
                # --- *** ADDED VALIDATION *** ---
                name = ai_data.get("sender_name")
                if not name or name.lower() in INVALID_NAMES:
                    logger.warning(f"AI extracted an invalid sender name: '{name}'. Re-asking")
                    await self.state_manager.safe_say("I didn't catch that name. " + prompts.PROMPT_FOR_SENDER_NAME)
                else:
                    self.message_job["sender_name"] = name
                    logger.info(f"Got sender name: {self.message_job['sender_name']}")
                    self.current_step = ConversationStep.AWAITING_RECIPIENT_NAME
                    await self.state_manager.safe_say(prompts.PROMPT_FOR_RECIPIENT_NAME)
            else:
                logger.warning(f"Expected PROVIDE_SENDER_NAME, but got {intent}. Re-asking")
                await self.state_manager.safe_say("I didn't quite catch that. " + prompts.PROMPT_FOR_SENDER_NAME)

        # --- 3. Awaiting Recipient Name ---
        elif self.current_step == ConversationStep.AWAITING_RECIPIENT_NAME:
            if intent == "PROVIDE_RECIPIENT_NAME":
                # --- *** ADDED VALIDATION *** ---
                name = ai_data.get("recipient_name")
                if not name or name.lower() in INVALID_NAMES:
                    logger.warning(f"AI extracted an invalid recipient name: '{name}'. Re-asking")
                    await self.state_manager.safe_say("I didn't catch that name. " + prompts.PROMPT_FOR_RECIPIENT_NAME)
                else:
                    self.message_job["recipient_name"] = name
                    logger.info(f"Got recipient name: {self.message_job['recipient_name']}")
                    self.current_step = ConversationStep.AWAITING_PROTECTION
                    await self.state_manager.safe_say(prompts.PROMPT_ASK_FOR_PROTECTION)
            else:
                await self.state_manager.safe_say("I didn't catch that. " + prompts.PROMPT_FOR_RECIPIENT_NAME)

        # --- 4. Awaiting Protection Confirmation ---
        elif self.current_step == ConversationStep.AWAITING_PROTECTION:
            if intent == "CONFIRM_YES":
                logger.info("User wants message protection")
                self.current_step = ConversationStep.AWAITING_PASSWORD
                await self.state_manager.safe_say(prompts.PROMPT_FOR_PASSWORD)
            elif intent == "CONFIRM_NO":
                logger.info("User does not want protection")
                self.current_step = ConversationStep.AWAITING_ADDRESS
                await self.state_manager.safe_say(prompts.PROMPT_FOR_ADDRESS)
            
            elif intent == "PROVIDE_PASSWORD":
                # --- *** ADDED VALIDATION *** ---
                password = ai_data.get("password")
                if not password:
                    logger.warning("AI detected PROVIDE_PASSWORD but extracted no entity. Re-asking")
                    await self.state_manager.safe_say("I heard you mention a password, but didn't catch it. Please say 'yes' or 'no' first")
                else:
                    logger.info("User jumped ahead, provided password directly")
                    self.message_job["password"] = password
                    self.current_step = ConversationStep.AWAITING_ADDRESS
                    await self.state_manager.safe_say(prompts.PROMPT_FOR_ADDRESS)
            
            else:
                await self.state_manager.safe_say("Please say 'yes' or 'no'. " + prompts.PROMPT_ASK_FOR_PROTECTION)

        # --- 5. Awaiting Password ---
        elif self.current_step == ConversationStep.AWAITING_PASSWORD:
            if intent == "PROVIDE_PASSWORD":
                # --- *** ADDED VALIDATION *** ---
                password = ai_data.get("password")
                if not password:
                    logger.warning("AI detected PROVIDE_PASSWORD but extracted no entity. Re-asking")
                    await self.state_manager.safe_say("I didn't quite get that. " + prompts.PROMPT_FOR_PASSWORD)
                else:
                    self.message_job["password"] = password
                    logger.info(f"Got password: {self.message_job['password']}")
                    self.current_step = ConversationStep.AWAITING_ADDRESS
                    await self.state_manager.safe_say(prompts.PROMPT_FOR_ADDRESS)
            else:
                await self.state_manager.safe_say("I didn't get that. " + prompts.PROMPT_FOR_PASSWORD)

        # --- 6. Awaiting Address ---
        elif self.current_step == ConversationStep.AWAITING_ADDRESS:
            if intent == "PROVIDE_ADDRESS":
                # --- *** ADDED VALIDATION *** ---
                address = ai_data.get("address_text")
                if not address:
                    logger.warning("AI detected PROVIDE_ADDRESS but extracted no entity. Re-asking")
                    await self.state_manager.safe_say("I didn't understand the address. " + prompts.PROMPT_FOR_ADDRESS)
                else:
                    self.message_job["address_text"] = address
                    logger.info(f"Got address: {self.message_job['address_text']}")
                    
                    # --- ALL INFO GATHERED ---
                    self.current_step = ConversationStep.READY_TO_SEND
                    self.completed_job = self.message_job
                    
                    # Generate a message ID
                    message_id = hash(self.message_job["message_body"]) & 0xfffff
                    self.completed_job["id"] = message_id
                    
                    logger.info(f"Message job complete: {self.completed_job}")
                    await self.state_manager.safe_say(
                        prompts.PROMPT_MESSAGE_ID_CONFIRM.format(message_id)
                    )
                    
                    # Reset flow back to idle
                    self.current_step = ConversationStep.IDLE
            else:
                await self.state_manager.safe_say("I didn't understand the address. " + prompts.PROMPT_FOR_ADDRESS)
    
    def is_in_conversation(self) -> bool:
        """Helper to check if a flow is active"""
        return self.current_step != ConversationStep.IDLE

    def get_completed_job(self) -> Optional[Dict[str, Any]]:
        """Used by the main loop to retrieve a finished job"""
        job = self.completed_job
        self.completed_job = None  # Clear job after retrieval
        return job