# File: robot/navigation/mapper.py

import asyncio
import json
import logging
import math
from typing import List, Dict

from robot.controller import RobotController
from config import settings
from mini.apis.api_action import MoveRobotDirection

# Setup logger for this module
logger = logging.getLogger(__name__)

# --- CRITICAL TUNING ---
# You calibrated this: 12 steps for a 360-degree turn.
STEPS_FOR_360_TURN = 12  # <--- THIS IS YOUR GOLDEN NUMBER

# --- FIX 1 ---
# The number of scans MUST equal the number of steps.
# Your robot is physically limited to 12 positions in a circle.
SCAN_POINTS = STEPS_FOR_360_TURN  # (This will be 12)


class Mapper:
    """
    Handles room scanning and map persistence.
    
    The "map" is a simple 2D point cloud, saved as a list of
    {"angle": degrees, "distance_mm": distance} objects.
    """

    def __init__(self, controller: 'RobotController'):
        self.controller = controller
        self.map_data: List[Dict] = []
        
        num_scan_points = SCAN_POINTS
        if num_scan_points <= 0:
            num_scan_points = 1
        
        # This will now calculate: ceil(12 / 12) = 1
        self.steps_per_scan = int(math.ceil(STEPS_FOR_360_TURN / num_scan_points))
        
        # This will now calculate: 360.0 / 12 = 30 degrees per step
        self.angle_per_scan = 360.0 / num_scan_points
        self.scan_points_to_run = num_scan_points  

    async def scan_and_build_map(self) -> bool:
        """
        Performs the 360-degree spin-and-scan operation.
        Saves the resulting map to the file specified in settings.
        """
        logger.info(f"Starting room scan: {self.scan_points_to_run} points, {self.steps_per_scan} steps per point.")
        self.map_data = []

        try:
            for i in range(self.scan_points_to_run):
                current_angle = round(i * self.angle_per_scan, 1)
                
                # 1. Get distance reading from the controller
                distance_mm = await self.controller.get_infrared_distance()
                
                if distance_mm is not None:
                    logger.debug(f"Scan {i}: angle={current_angle}°, distance={distance_mm}mm")
                    self.map_data.append({"angle": current_angle, "distance_mm": distance_mm})
                else:
                    logger.warning(f"Scan {i} at angle {current_angle}°: Failed to get IR reading.")
                
                # --- FIX 2 ---
                # Rotate to the next scan point.
                # We remove the 'if' check to ensure the robot performs
                # all 12 steps to complete the full 360-degree circle.
                await self.controller.move(MoveRobotDirection.LEFTWARD, self.steps_per_scan)
                
                # Give the robot a moment to stabilize after moving
                await asyncio.sleep(0.2) 

            # 3. Save the completed map to a file
            self._save_map_to_file()
            logger.info(f"Room scan complete. Map saved to {settings.MAP_FILE_PATH}")
            return True

        except Exception as e:
            logger.error(f"An error occurred during room scan: {e}", exc_info=True)
            return False

    def _save_map_to_file(self):
        """
        Saves the collected map_data to a JSON file.
        """
        try:
            with open(settings.MAP_FILE_PATH, 'w') as f:
                json.dump(self.map_data, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to save map file to {settings.MAP_FILE_PATH}: {e}")

    def load_map_from_file(self) -> bool:
        """
        Loads a previously saved map from the JSON file.
        """
        try:
            with open(settings.MAP_FILE_PATH, 'r') as f:
                self.map_data = json.load(f)
            logger.info(f"Successfully loaded map from {settings.MAP_FILE_PATH}")
            return True
        except FileNotFoundError:
            logger.warning(f"No map file found at {settings.MAP_FILE_PATH}. A new scan is needed.")
            self.map_data = []
            return False
        except Exception as e:
            logger.error(f"Failed to load or parse map file: {e}")
            self.map_data = []
            return False