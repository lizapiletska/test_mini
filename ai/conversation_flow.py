import asyncio
import logging
from enum import Enum, auto
from typing import Optional, Dict, Any, TYPE_CHECKING

from config import prompts

# Avoid circular imports for type hinting
if TYPE_CHECKING:
    from core.state_manager import StateManager
    # --- *** NEW *** ---
    from ai.memory import MemoryManager

logger = logging.getLogger(__name__)

INVALID_NAMES = ["this", "for", "a", "an", "the", "is", "to", "message"]

class ConversationStep(Enum):
    IDLE = auto()
    AWAITING_MESSAGE_BODY = auto()
    AWAITING_SENDER_NAME = auto()
    AWAITING_RECIPIENT_NAME = auto()
    AWAITING_PROTECTION = auto()
    AWAITING_PASSWORD = auto()
    AWAITING_ADDRESS = auto()
    READY_TO_SEND = auto()


class ConversationFlow:
    """
    Manages the stateful, multi-step conversation for composing a message.
    """

    def __init__(self, state_manager: 'StateManager'):
        self.state_manager = state_manager
        # --- *** NEW *** ---
        # Get the memory manager instance from the state manager
        self.memory: 'MemoryManager' = self.state_manager.memory
        
        self.current_step = ConversationStep.IDLE
        self.message_job: Dict[str, Any] = {}
        self.completed_job: Optional[Dict[str, Any]] = None

    def start_new_message_flow(self, initial_ai_data: Dict[str, Any]):
        """
        Kicks off the conversation from a "SEND_MESSAGE" intent.
        (Function unchanged)
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
        
        self.current_step = ConversationStep.AWAITING_MESSAGE_BODY
        asyncio.create_task(self.state_manager.safe_say(prompts.PROMPT_FOR_MESSAGE))

    async def handle_ai_response(self, ai_data: Dict[str, Any]):
        """
        The main state machine.
        (Only one change in step 6)
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
                    
                    message_id = hash(self.message_job["message_body"]) & 0xfffff
                    self.completed_job["id"] = message_id
                    
                    logger.info(f"Message job complete: {self.completed_job}")

                    # --- *** NEW *** ---
                    # Save the composing conversation to its file.
                    self.memory.finalize_conversation_log(str(message_id))
                    
                    await self.state_manager.safe_say(
                        prompts.PROMPT_MESSAGE_ID_CONFIRM.format(message_id)
                    )
                    
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