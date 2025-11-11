# File: robot/navigation/obstacle_detector.py

import logging
from typing import TYPE_CHECKING

from config import settings

# Avoid circular imports for type hinting
if TYPE_CHECKING:
    from robot.controller import RobotController

# Setup logger for this module
logger = logging.getLogger(__name__)


class ObstacleDetector:
    """
    Provides a simple, real-time safety check for navigation.
    
    It uses the controller to read the infrared sensor and
    compares it against the safety threshold defined in settings.
    """

    def __init__(self, controller: 'RobotController'):
        """
        Initializes the detector with the robot controller and the safety threshold.
        """
        self.controller = controller
        # Load the safety distance (e.g., 300mm) from your config file
        self.threshold_mm = settings.OBSTACLE_THRESHOLD_MM
        logger.info(f"Obstacle detector initialized with threshold: {self.threshold_mm}mm")

    async def is_path_blocked(self) -> bool:
        """
        Checks if an obstacle is dangerously close to the front of the robot.
        
        Returns:
            True: If an obstacle is detected OR if the sensor fails (fail-safe).
            False: If the path is clear.
        """
        logger.debug("Checking for obstacles...")
        
        distance_mm = await self.controller.get_infrared_distance()

        if distance_mm is None:
            # --- FAIL-SAFE ---
            # If the sensor fails to return a value, we MUST assume
            # the path is blocked. Never move blind.
            logger.warning("Sensor read failed! Assuming path is blocked for safety.")
            return True

        if distance_mm < self.threshold_mm:
            # An obstacle is too close.
            logger.warning(
                f"OBSTACLE DETECTED! Distance: {distance_mm}mm "
                f"(Threshold: {self.threshold_mm}mm)"
            )
            return True

        # Path is clear
        logger.debug(f"Path is clear. Distance: {distance_mm}mm")
        return False