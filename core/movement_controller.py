# File: core/movement_controller.py

import logging
from typing import TYPE_CHECKING
from mini.apis.api_action import MoveRobotDirection

# Avoid circular imports
if TYPE_CHECKING:
    from robot.controller import RobotController
    from core.robot_state import RobotState
    from vision.visual_mapper import VisualMapper

logger = logging.getLogger(__name__)

class MovementController:
    """
    This is the new "safe_move". It is the *only* module
    that should call the robot's move function.
    
    It automatically updates the RobotState and VisualMapper
    after every physical move.
    """
    
    def __init__(self,
                 controller: 'RobotController',
                 robot_state: 'RobotState',
                 visual_mapper: 'VisualMapper'):
        self.controller = controller
        self.robot_state = robot_state
        self.visual_mapper = visual_mapper

    async def move(self, direction: MoveRobotDirection, steps: int):
        """
        Executes a move and updates all state-tracking modules.
        """
        try:
            # 1. Execute the physical move
            success = await self.controller.move(direction, steps)
            
            if success:
                # 2. Update the internal state tracker
                self.robot_state.move(direction, steps)
                
                # 3. Get the new state
                x, y, heading = self.robot_state.get_state()
                
                # 4. Update the live visual map
                self.visual_mapper.update_robot_state(x, y, heading)
            else:
                logger.warning(f"Physical move {direction.name} failed. State not updated.")
                
        except Exception as e:
            logger.error(f"Error during guarded move: {e}", exc_info=True)