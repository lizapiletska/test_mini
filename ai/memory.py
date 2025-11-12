# File: ai/memory.py

import json
import logging
import os
import glob # <-- NEW
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import settings
from robot.navigation.planner import RoutePlan
from mini.apis.api_action import MoveRobotDirection

logger = logging.getLogger(__name__)

ProfileDatabase = Dict[str, Dict[str, Any]]


class MemoryManager:
    """
    Manages long-term memory of user profiles (including coordinates)
    and short-term memory of conversation history.
    """

    def __init__(self):
        self.profiles_dir = settings.PROFILES_DIRECTORY
        self.messages_dir = settings.MESSAGES_DIRECTORY
        
        os.makedirs(self.profiles_dir, exist_ok=True)
        os.makedirs(self.messages_dir, exist_ok=True)
        
        self._temp_conversation_log: List[Dict[str, str]] = []
        
        logger.info(f"MemoryManager initialized.")
        logger.info(f"Profile directory: {self.profiles_dir}")
        logger.info(f"Messages directory: {self.messages_dir}")

    def _get_profile_path(self, name: str) -> str:
        # (Unchanged)
        safe_name = "".join(c for c in name if c.isalnum()).lower()
        if not safe_name:
            safe_name = "unknown"
        return os.path.join(self.profiles_dir, f"profile_{safe_name}.json")

    def _get_message_log_path(self, message_id: str) -> str:
        # (Unchanged)
        return os.path.join(self.messages_dir, f"log_{message_id}.json")

    # --- Conversation Log Functions (Unchanged) ---

    def start_conversation_log(self):
        logger.info("Starting new conversation log.")
        self._temp_conversation_log = []

    def load_conversation_log(self, message_id: str):
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

    def log_exchange(self, speaker: str, text: str):
        if not text:
            return
        exchange = {
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker,
            "text": text
        }
        self._temp_conversation_log.append(exchange)

    def finalize_conversation_log(self, message_id: str):
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
        self._temp_conversation_log = []

    # --- Profile & Route Functions (MODIFIED) ---

    def get_known_route_for_recipient(self, name: str) -> Optional[RoutePlan]:
        # (Unchanged)
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

    # --- *** MODIFIED FUNCTION *** ---
    def save_route_for_recipient(self, 
                                 name: str, 
                                 route: RoutePlan, 
                                 x: float, 
                                 y: float, 
                                 heading: float):
        """
        Saves a successful delivery route AND the final coordinates
        to a recipient's profile.
        """
        profile_path = self._get_profile_path(name)
        
        serializable_route = [[direction.name, steps] for direction, steps in route]
        
        profile_data = {
            "name": name,
            "saved_route": serializable_route,
            # --- *** NEW *** ---
            "location": {
                "x": round(x, 2),
                "y": round(y, 2),
                "heading": round(heading, 1)
            },
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open(profile_path, 'w') as f:
                json.dump(profile_data, f, indent=4)
            logger.info(f"Successfully saved new route and location for {name} to {profile_path}")
        except IOError as e:
            logger.error(f"Failed to save profile for {name}: {e}")

    # --- *** NEW FUNCTION *** ---
    def get_all_saved_locations(self) -> List[Dict[str, Any]]:
        """
        Loads all saved profiles and returns their names and locations.
        """
        locations = []
        profile_pattern = os.path.join(self.profiles_dir, "profile_*.json")
        
        for profile_path in glob.glob(profile_pattern):
            try:
                with open(profile_path, 'r') as f:
                    data = json.load(f)
                    if "name" in data and "location" in data:
                        locations.append(data)
                        logger.info(f"Loaded saved location for {data['name']}")
            except Exception as e:
                logger.error(f"Error loading profile {profile_path}: {e}")
                
        return locations