import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import settings
# We need the type definition for a route from the planner
from robot.navigation.planner import RoutePlan
# We need this to deserialize the route
from mini.apis.api_action import MoveRobotDirection

# Setup logger for this module
logger = logging.getLogger(__name__)

# This will be our simple in-memory cache
# e.g., {"person_b": {"name": "Person B", "saved_route": [...]}}
ProfileDatabase = Dict[str, Dict[str, Any]]


class MemoryManager:
    """
    Manages long-term memory of user profiles and short-term
    memory of conversation history.
    """

    def __init__(self):
        self.profiles_dir = settings.PROFILES_DIRECTORY
        # --- *** NEW *** ---
        self.messages_dir = settings.MESSAGES_DIRECTORY
        
        # Ensure the data directories exist
        os.makedirs(self.profiles_dir, exist_ok=True)
        os.makedirs(self.messages_dir, exist_ok=True)
        
        # --- *** NEW *** ---
        # This will hold the current conversation in memory
        self._temp_conversation_log: List[Dict[str, str]] = []
        
        logger.info(f"MemoryManager initialized.")
        logger.info(f"Profile directory: {self.profiles_dir}")
        logger.info(f"Messages directory: {self.messages_dir}")

    def _get_profile_path(self, name: str) -> str:
        """Generates a safe filename for a profile based on the name."""
        safe_name = "".join(c for c in name if c.isalnum()).lower()
        if not safe_name:
            safe_name = "unknown"
        return os.path.join(self.profiles_dir, f"profile_{safe_name}.json")

    # --- *** NEW *** ---
    def _get_message_log_path(self, message_id: str) -> str:
        """Generates a standard file path for a message log."""
        return os.path.join(self.messages_dir, f"log_{message_id}.json")

    # --- *** NEW *** ---
    def start_conversation_log(self):
        """
        Clears the temporary log to begin recording a new conversation.
        This is called when the "SEND_MESSAGE" intent is first heard.
        """
        logger.info("Starting new conversation log.")
        self._temp_conversation_log = []

    # --- *** NEW *** ---
    def load_conversation_log(self, message_id: str):
        """
        Loads a finalized (composing) log from disk into the temporary
        log, so the (delivery) conversation can be appended.
        """
        log_path = self._get_message_log_path(str(message_id))
        try:
            with open(log_path, 'r') as f:
                self._temp_conversation_log = json.load(f)
            logger.info(f"Loaded conversation log {log_path} for appending.")
        except FileNotFoundError:
            logger.warning(f"No log file found for {message_id}. Starting a new log.")
            self.start_conversation_log()
        except Exception as e:
            logger.error(f"Error loading log file {log_path}: {e}")
            self.start_conversation_log()

    # --- *** NEW *** ---
    def log_exchange(self, speaker: str, text: str):
        """
        Adds a single line of dialogue (from 'user' or 'robot')
        to the temporary in-memory log.
        """
        if not text: # Don't log empty speech
            return
            
        exchange = {
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker,
            "text": text
        }
        self._temp_conversation_log.append(exchange)

    # --- *** NEW *** ---
    def finalize_conversation_log(self, message_id: str):
        """
        Saves the entire temporary log to a file, named with the message_id.
        This will overwrite any existing file, saving the complete history.
        """
        if not self._temp_conversation_log:
            logger.warning("No conversation to finalize.")
            return

        log_path = self._get_message_log_path(str(message_id))
        try:
            with open(log_path, 'w') as f:
                json.dump(self._temp_conversation_log, f, indent=4)
            logger.info(f"Conversation log saved to {log_path}")
        except IOError as e:
            logger.error(f"Failed to save conversation log to {log_path}: {e}")
        
        # Finally, clear the temporary log
        self._temp_conversation_log = []

    def get_known_route_for_recipient(self, name: str) -> Optional[RoutePlan]:
        """
        Checks if a recipient is known and has a saved route.
        (Function unchanged)
        """
        profile_path = self._get_profile_path(name)
        try:
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
            
            saved_route = profile_data.get("saved_route")
            if saved_route:
                logger.info(f"Found saved route for recipient: {name}")
                return [(MoveRobotDirection[direction_name], steps)
                        for direction_name, steps in saved_route]
            return None
            
        except FileNotFoundError:
            logger.info(f"No profile found for recipient: {name}")
            return None
        except Exception as e:
            logger.error(f"Error loading profile for {name}: {e}")
            return None

    def save_route_for_recipient(self, name: str, route: RoutePlan):
        """
        Saves a successful delivery route to a recipient's profile.
        (Function unchanged)
        """
        profile_path = self._get_profile_path(name)
        
        serializable_route = [[direction.name, steps] for direction, steps in route]
        
        profile_data = {
            "name": name,
            "saved_route": serializable_route,
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open(profile_path, 'w') as f:
                json.dump(profile_data, f, indent=4)
            logger.info(f"Successfully saved new route for {name} to {profile_path}")
        except IOError as e:
            logger.error(f"Failed to save profile for {name}: {e}")