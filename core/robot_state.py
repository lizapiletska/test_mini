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
        self.x_m: float = 0.0  # Robot's X position in meters
        self.y_m: float = 0.0  # Robot's Y position in meters
        self.heading_deg: float = 0.0  # Robot's heading in degrees (0 = +Y, 90 = +X)

        # User's calibration data
        # We add (0, 0) to handle 0-step inputs
        self.step_keys = np.array([0, 1, 2, 5, 10, 20])
        self.dist_vals_cm = np.array([0, 2.5, 5.0, 12.0, 23.0, 48.0])
        
        logger.info(f"RobotState initialized at (0, 0) with heading 0 deg.")

    def _convert_steps_to_meters(self, steps: int) -> float:
        """
        Converts a step count to meters using linear interpolation
        based on the user's calibration data.
        """
        # np.interp handles any step value (e.g., 7, 15, 50)
        # by interpolating between the known points.
        cm = np.interp(steps, self.step_keys, self.dist_vals_cm)
        return cm / 100.0  # Convert cm to meters

    def move(self, direction: MoveRobotDirection, steps: int):
        """
        Updates the robot's internal state (x, y, heading)
        after a physical move.
        """
        if direction == MoveRobotDirection.LEFTWARD:
            self.heading_deg = (self.heading_deg - steps) % 360
            logger.debug(f"State Updated: New Heading = {self.heading_deg:.1f}°")
            
        elif direction == MoveRobotDirection.RIGHTWARD:
            self.heading_deg = (self.heading_deg + steps) % 360
            logger.debug(f"State Updated: New Heading = {self.heading_deg:.1f}°")
            
        else:
            # Get the real distance moved, in meters
            distance_m = self._convert_steps_to_meters(steps)
            
            # Adjust distance if moving backward
            if direction == MoveRobotDirection.BACKWARD:
                distance_m = -distance_m

            # Calculate movement in (dx, dy)
            # We use (90 - heading) to convert "compass" heading to "math" angle
            math_angle_rad = np.deg2rad(90 - self.heading_deg)
            
            dx = distance_m * np.cos(math_angle_rad)
            dy = distance_m * np.sin(math_angle_rad)
            
            self.x_m += dx
            self.y_m += dy
            logger.debug(f"State Updated: New (x, y) = ({self.x_m:.2f}, {self.y_m:.2f})")
            
    def get_world_coords(self, angle_deg: float, distance_mm: int) -> (float, float):
        """
        Converts a sensor reading (relative to robot) into
        absolute (x, y) world coordinates.
        """
        distance_m = distance_mm / 1000.0
        
        # Calculate the absolute angle of the sensor reading
        absolute_angle_deg = self.heading_deg + angle_deg
        
        # Convert to math angle
        math_angle_rad = np.deg2rad(90 - absolute_angle_deg)
        
        # Calculate obstacle's (x, y) relative to robot's center
        obstacle_x = self.x_m + (distance_m * np.cos(math_angle_rad))
        obstacle_y = self.y_m + (distance_m * np.sin(math_angle_rad))
        
        return (obstacle_x, obstacle_y)

    def get_state(self) -> (float, float, float):
        """Returns the current (x_m, y_m, heading_deg)"""
        return self.x_m, self.y_m, self.heading_deg