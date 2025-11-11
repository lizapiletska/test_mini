# File: ai/memory.py

import json
import logging
import os
from datetime import datetime  # <-- *** FIX: Added missing import ***
from typing import Optional, Dict, Any

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
    Manages long-term memory of user profiles, including
    known recipients and their saved delivery routes.
    """

    def __init__(self):
        self.profiles_dir = settings.PROFILES_DIRECTORY
        # Ensure the data directory exists
        os.makedirs(self.profiles_dir, exist_ok=True)
        logger.info(f"MemoryManager initialized. Profile directory: {self.profiles_dir}")

    def _get_profile_path(self, name: str) -> str:
        """Generates a safe filename for a profile based on the name."""
        safe_name = "".join(c for c in name if c.isalnum()).lower()
        if not safe_name:
            safe_name = "unknown"
        return os.path.join(self.profiles_dir, f"profile_{safe_name}.json")

    def get_known_route_for_recipient(self, name: str) -> Optional[RoutePlan]:
        """
        Checks if a recipient is known and has a saved route.
        
        Args:
            name: The name of the recipient (e.g., "Person B").
        
        Returns:
            The saved RoutePlan if one exists, otherwise None.
        """
        profile_path = self._get_profile_path(name)
        try:
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
            
            saved_route = profile_data.get("saved_route")
            if saved_route:
                logger.info(f"Found saved route for recipient: {name}")
                # We must convert the saved list of [str, int] back into [Enum, int]
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
        
        Args:
            name: The name of the recipient.
            route: The successful RoutePlan from the Planner.
        """
        profile_path = self._get_profile_path(name)
        
        # Convert Enum to string for safe JSON serialization
        # (MoveRobotDirection.FORWARD, 50) -> ["FORWARD", 50]
        serializable_route = [[direction.name, steps] for direction, steps in route]
        
        profile_data = {
            "name": name,
            "saved_route": serializable_route,
            # Use isoformat() for a standard, readable timestamp
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open(profile_path, 'w') as f:
                json.dump(profile_data, f, indent=4)
            logger.info(f"Successfully saved new route for {name} to {profile_path}")
        except IOError as e:
            logger.error(f"Failed to save profile for {name}: {e}")