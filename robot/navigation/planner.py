# File: robot/navigation/planner.py

import re
import logging
from typing import List, Tuple, Optional

# Import the SDK's definitions for movement
from mini.apis.api_action import MoveRobotDirection

# Setup logger for this module
logger = logging.getLogger(__name__)

# This list defines the route plan.
# It's a list of (Direction, Steps) tuples.
RoutePlan = List[Tuple[MoveRobotDirection, int]]

class Planner:
    """
    Parses natural language navigation commands from the AI into an
    executable route plan for the RobotController.
    """

    def __init__(self):
        # We define simple regex patterns to find commands in the text.
        # This looks for "forward", "back", "backward"
        self.forward_pattern = re.compile(r'forward|forwar|foward')
        self.backward_pattern = re.compile(r'backward|back|backwards')
        
        # This looks for "left" or "90 left"
        self.left_pattern = re.compile(r'left|leftward')
        # This looks for "right" or "90 right"
        self.right_pattern = re.compile(r'right|rightward')
        
        # This finds any number (e.g., "50", "90")
        self.number_pattern = re.compile(r'\d+')

    def parse_address_to_route(self, text: str) -> Optional[RoutePlan]:
        """
        Main parsing method.
        
        Input: "Turn to left 12 steps forward"
        Output: [ (MoveRobotDirection.LEFTWARD, 90), 
                  (MoveRobotDirection.FORWARD, 12) ]
        """
        logger.info(f"Parsing address string: '{text}'")
        
        # --- *** THIS IS THE FIX *** ---
        # We split by "and" or "then" to get command chunks. "turn" is part of a command.
        commands = re.split(r'\s+then\s+|\s+and\s+', text.lower())
        
        route_plan: RoutePlan = []
        
        for command in commands:
            if not command.strip():
                continue
            
            logger.debug(f"Parsing command chunk: '{command}'")
            
            # This chunk might contain multiple instructions, e.g., "turn left 12 steps forward"
            # We check for all of them, not just the first one.
            
            # 1. Check for turns. Default to 90 degrees if no number is found.
            if self.left_pattern.search(command):
                number_match = self.number_pattern.search(command)
                # If "forward" or "back" is also in the command, the number belongs to them.
                if self.forward_pattern.search(command) or self.backward_pattern.search(command):
                    value = 90 # Default turn
                else:
                    value = int(number_match.group(0)) if number_match else 90
                route_plan.append((MoveRobotDirection.LEFTWARD, value))

            if self.right_pattern.search(command):
                number_match = self.number_pattern.search(command)
                if self.forward_pattern.search(command) or self.backward_pattern.search(command):
                    value = 90 # Default turn
                else:
                    value = int(number_match.group(0)) if number_match else 90
                route_plan.append((MoveRobotDirection.RIGHTWARD, value))
            
            # 2. Check for movement. These commands MUST have a number.
            if self.forward_pattern.search(command):
                number_match = self.number_pattern.search(command)
                if number_match:
                    value = int(number_match.group(0))
                    route_plan.append((MoveRobotDirection.FORWARD, value))
                else:
                    logger.warning(f"Forward command chunk '{command}' has no number, skipping move.")
            
            if self.backward_pattern.search(command):
                number_match = self.number_pattern.search(command)
                if number_match:
                    value = int(number_match.group(0))
                    route_plan.append((MoveRobotDirection.BACKWARD, value))
                else:
                    logger.warning(f"Backward command chunk '{command}' has no number, skipping move.")

        if not route_plan:
            logger.error(f"Failed to create any valid route from text: '{text}'")
            return None

        logger.info(f"Successfully parsed route: {route_plan}")
        return route_plan