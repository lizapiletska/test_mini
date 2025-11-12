# File: core/robot_state.py

import logging
import math
import numpy as np
from mini.apis.api_action import MoveRobotDirection

logger = logging.getLogger(__name__)

class RobotState:
    """
    Tracks the robot's precise (x, y) position and heading
    in a 2D coordinate system (in meters).
    """
    def __init__(self):
        self.x_m: float = 0.0
        self.y_m: float = 0.0
        self.heading_deg: float = 0.0

        # Calibration for TURNING
        self.angle_per_turn_step_deg: float = 360.0 / 12.0  # 30.0 degrees per step

        # Calibration for FORWARD/BACKWARD
        self.step_keys = np.array([0, 1, 2, 5, 10, 20])
        self.dist_vals_cm = np.array([0, 2.5, 5.0, 12.0, 23.0, 48.0])
        
        logger.info(f"RobotState initialized at (0, 0) with heading 0 deg.")
        logger.info(f"Turning calibration: {self.angle_per_turn_step_deg} deg/step.")

    def _convert_steps_to_meters(self, steps: int) -> float:
        """
        Converts a step count to meters using linear interpolation.
        (This is ONLY for FORWARD/BACKWARD)
        """
        cm = np.interp(steps, self.step_keys, self.dist_vals_cm)
        return cm / 100.0

    def move(self, direction: MoveRobotDirection, steps: int):
        """
        Updates the robot's internal state (x, y, heading)
        after a physical move.
        (This function is correct from last time)
        """
        if direction == MoveRobotDirection.LEFTWARD:
            degrees_to_turn = steps * self.angle_per_turn_step_deg
            self.heading_deg = (self.heading_deg - degrees_to_turn) % 360
            logger.debug(f"State Updated: Turned left {steps} steps ({degrees_to_turn:.1f} deg). New Heading = {self.heading_deg:.1f}°")
            
        elif direction == MoveRobotDirection.RIGHTWARD:
            degrees_to_turn = steps * self.angle_per_turn_step_deg
            self.heading_deg = (self.heading_deg + degrees_to_turn) % 360
            logger.debug(f"State Updated: Turned right {steps} steps ({degrees_to_turn:.1f} deg). New Heading = {self.heading_deg:.1f}°")
            
        else:
            distance_m = self._convert_steps_to_meters(steps)
            
            if direction == MoveRobotDirection.BACKWARD:
                distance_m = -distance_m

            math_angle_rad = np.deg2rad(90 - self.heading_deg)
            
            dx = distance_m * np.cos(math_angle_rad)
            dy = distance_m * np.sin(math_angle_rad)
            
            self.x_m += dx
            self.y_m += dy
            logger.debug(f"State Updated: New (x, y) = ({self.x_m:.2f}, {self.y_m:.2f})")
            
    # --- *** MODIFIED FUNCTION *** ---
    def get_world_coords(self, distance_mm: int) -> (float, float):
        """
        Converts a sensor reading (from the 0-degree-relative
        front sensor) into absolute (x, y) world coordinates.
        """
        distance_m = distance_mm / 1000.0
        
        # The sensor angle is 0, so the absolute angle *is* the robot's heading
        absolute_angle_deg = self.heading_deg
        
        # Convert to math angle
        math_angle_rad = np.deg2rad(90 - absolute_angle_deg)
        
        # Calculate obstacle's (x, y) relative to robot's center
        obstacle_x = self.x_m + (distance_m * np.cos(math_angle_rad))
        obstacle_y = self.y_m + (distance_m * np.sin(math_angle_rad))
        
        return (obstacle_x, obstacle_y)

    def get_state(self) -> (float, float, float):
        """Returns the current (x_m, y_m, heading_deg)"""
        return self.x_m, self.y_m, self.heading_deg