# File: robot/movement/route_recorder.py

import logging
from typing import Optional

from config import settings
from robot.navigation.planner import RoutePlan
from mini.apis.api_action import MoveRobotDirection

# Setup logger for this module
logger = logging.getLogger(__name__)

# This map is now ONLY for turns.
OPPOSITE_TURNS = {
    MoveRobotDirection.LEFTWARD: MoveRobotDirection.RIGHTWARD,
    MoveRobotDirection.RIGHTWARD: MoveRobotDirection.LEFTWARD,
}

# Based on your robot's calibration (12 steps = 360 deg)
STEPS_FOR_180_TURN = 6


class RouteRecorder:
    """
    Records a completed route and calculates the inverse route
    for the robot to return to its starting point.
    """

    def __init__(self):
        self.last_route: Optional[RoutePlan] = None
        logger.info("RouteRecorder initialized.")

    def save_route_for_return(self, route: RoutePlan):
        """
        Call this *before* the robot starts moving to save the plan.
        """
        logger.info(f"Saving route for return trip: {route}")
        self.last_route = route

    def get_return_route(self) -> Optional[RoutePlan]:
        """
        Calculates the reverse of the last saved route.
        
        - Turns (Left/Right) are inverted.
        - Moves (Forward/Backward) are reversed by turning 180,
          repeating the move, and turning 180 again.
        """
        if not self.last_route:
            logger.warning("Cannot get return route: No route was saved.")
            return None

        return_route: RoutePlan = []
        
        # Go through the original route *in reverse*
        for (direction, steps) in reversed(self.last_route):
            
            # Check if it's a simple turn
            opposite_turn = OPPOSITE_TURNS.get(direction)
            
            if opposite_turn:
                # Case 1: It's a turn (LEFTWARD or RIGHTWARD)
                return_route.append((opposite_turn, steps))
                
            elif direction == MoveRobotDirection.FORWARD or direction == MoveRobotDirection.BACKWARD:
                # Case 2: It's a move (FORWARD or BACKWARD)
                
                # --- *** MODIFIED LOGIC *** ---
                # 1. Turn 180 degrees
                return_route.append((MoveRobotDirection.LEFTWARD, STEPS_FOR_180_TURN))
                
                # 2. Perform the *same* move (which is now in the opposite direction)
                return_route.append((direction, steps))
                
                # 3. Turn 180 degrees again to reset orientation
                return_route.append((MoveRobotDirection.LEFTWARD, STEPS_FOR_180_TURN))
                # --- *** END MODIFIED LOGIC *** ---
                
            else:
                logger.warning(f"Unknown direction '{direction}' in route, skipping.")
            
        logger.info(f"Generated smart return route: {return_route}")
        self.last_route = None
        
        return return_route