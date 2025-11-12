# File: robot/navigation/planner.py

import re
import logging
from typing import List, Tuple, Optional, Dict, Any

# Import the SDK's definitions for movement
from mini.apis.api_action import MoveRobotDirection

# Setup logger for this module
logger = logging.getLogger(__name__)

# This list defines the route plan.
# It's a list of (Direction, Steps) tuples.
RoutePlan = List[Tuple[MoveRobotDirection, int]]

# Your robot's turning calibration
ANGLE_PER_TURN_STEP_DEG = 360.0 / 12.0  # 30.0 degrees per step


class Planner:
    """
    Translates an AI-generated JSON route plan into an
    executable RoutePlan for the RobotController.
    """

    def __init__(self):
        """
        Initializes the planner with a mapping from AI string commands
        to the robot's SDK Enum values.
        """
        logger.info("Planner initialized. Will parse AI route_plan JSON.")
        self.direction_map = {
            "FORWARD": MoveRobotDirection.FORWARD,
            "BACKWARD": MoveRobotDirection.BACKWARD,
            "LEFTWARD": MoveRobotDirection.LEFTWARD,
            "RIGHTWARD": MoveRobotDirection.RIGHTWARD,
        }

    def _convert_degrees_to_steps(self, degrees: int) -> int:
        """
        Converts a degree value from the AI into the
        robot's hardware steps.
        """
        if degrees <= 0:
            return 1  # Minimum 1 step
        
        # Calculate steps and round to the nearest whole step
        steps = int(round(degrees / ANGLE_PER_TURN_STEP_DEG))
        return max(1, steps) # Ensure at least 1 step is returned

    def parse_plan_to_route(self, ai_plan: List[Dict[str, Any]]) -> Optional[RoutePlan]:
        """
        Parses the AI-generated route_plan JSON array into an
        executable RoutePlan.
        
        Input: [
            {"direction": "FORWARD", "value": 5},
            {"direction": "LEFTWARD", "value": None}  <-- This is the bug
        ]
        Output: [
            (MoveRobotDirection.FORWARD, 5),
            (MoveRobotDirection.LEFTWARD, 3)  <-- This is the fix
        ]
        """
        if not ai_plan:
            logger.error("AI route_plan is empty or None.")
            return None
        
        route_plan: RoutePlan = []
        
        for i, step in enumerate(ai_plan):
            try:
                direction_str = step.get("direction").upper()
                sdk_direction = self.direction_map[direction_str]
                value = step.get("value") # Get value, might be None

                # --- *** MODIFIED (DEFENSIVE) LOGIC *** ---
                if sdk_direction in (MoveRobotDirection.LEFTWARD, MoveRobotDirection.RIGHTWARD):
                    # It's a turn
                    if value is None:
                        logger.warning(f"Step {i}: AI gave no value for {direction_str}. Defaulting to 90 degrees.")
                        value = 90 # The defensive default
                    
                    turn_steps = self._convert_degrees_to_steps(int(value))
                    route_plan.append((sdk_direction, turn_steps))

                elif sdk_direction in (MoveRobotDirection.FORWARD, MoveRobotDirection.BACKWARD):
                    # It's a move
                    if value is None:
                        # This is a real error, we can't guess the steps
                        logger.error(f"Step {i}: AI gave no value for {direction_str}. Skipping step.")
                        continue # Skip this step
                    
                    route_plan.append((sdk_direction, int(value)))
                # --- *** END MODIFIED LOGIC *** ---
                
            except Exception as e:
                logger.error(f"Error parsing step {i}: {step}. Error: {e}", exc_info=True)
                continue  # Skip this bad step
                
        if not route_plan:
            logger.error(f"Failed to create any valid route from AI plan: {ai_plan}")
            return None
            
        logger.info(f"Successfully parsed AI plan into route: {route_plan}")
        return route_plan