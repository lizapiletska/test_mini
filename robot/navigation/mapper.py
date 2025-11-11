# File: robot/navigation/mapper.py

import asyncio
import json
import logging
import math
from typing import List, Dict, TYPE_CHECKING, Optional

from robot.controller import RobotController
from config import settings
from mini.apis.api_action import MoveRobotDirection

# --- *** NEW *** ---
# Import VisualMapper for type hinting
if TYPE_CHECKING:
    from vision.visual_mapper import VisualMapper

# Setup logger for this module
logger = logging.getLogger(__name__)

STEPS_FOR_360_TURN = 12
SCAN_POINTS = STEPS_FOR_360_TURN


class Mapper:
    """
    Handles room scanning and map persistence.
    Now also sends data to a live visualizer.
    """

    # --- *** MODIFIED *** ---
    def __init__(self, controller: 'RobotController', visual_mapper: Optional['VisualMapper'] = None):
        self.controller = controller
        self.map_data: List[Dict] = []
        
        # --- *** NEW *** ---
        self.visual_mapper = visual_mapper # Store the visualizer instance
        
        num_scan_points = SCAN_POINTS
        if num_scan_points <= 0:
            num_scan_points = 1
        
        self.steps_per_scan = int(math.ceil(STEPS_FOR_360_TURN / num_scan_points))
        self.angle_per_scan = 360.0 / num_scan_points
        self.scan_points_to_run = num_scan_points  

    async def scan_and_build_map(self) -> bool:
        """
        Performs the 360-degree spin-and-scan operation.
        Saves the resulting map AND updates the live visualizer.
        """
        logger.info(f"Starting room scan: {self.scan_points_to_run} points, {self.steps_per_scan} steps per point.")
        self.map_data = []

        # --- *** NEW *** ---
        # Start the visualizer window if it exists
        if self.visual_mapper:
            self.visual_mapper.start()

        try:
            for i in range(self.scan_points_to_run):
                current_angle = round(i * self.angle_per_scan, 1)
                
                # 1. Get distance reading
                distance_mm = await self.controller.get_infrared_distance()
                
                if distance_mm is not None:
                    logger.debug(f"Scan {i}: angle={current_angle}°, distance={distance_mm}mm")
                    self.map_data.append({"angle": current_angle, "distance_mm": distance_mm})
                else:
                    logger.warning(f"Scan {i} at angle {current_angle}°: Failed to get IR reading.")
                
                # --- *** NEW *** ---
                # Send data to the live visualizer
                if self.visual_mapper:
                    self.visual_mapper.update_map(current_angle, distance_mm, current_angle)

                # 2. Rotate to the next scan point
                await self.controller.move(MoveRobotDirection.LEFTWARD, self.steps_per_scan)
                
                # --- *** NEW *** ---
                # Update visualizer again to show the *new* heading after turning
                next_heading = round((i + 1) * self.angle_per_scan, 1)
                if self.visual_mapper:
                    # Send None for distance so it only updates the heading
                    self.visual_mapper.update_map(current_angle, None, next_heading)

                await asyncio.sleep(0.2) 

            # 3. Save the completed map to a file
            self._save_map_to_file()
            logger.info(f"Room scan complete. Map saved to {settings.MAP_FILE_PATH}")
            return True

        except Exception as e:
            logger.error(f"An error occurred during room scan: {e}", exc_info=True)
            return False
        
        finally:
            # --- *** NEW *** ---
            # Stop the visualizer thread
            if self.visual_mapper:
                self.visual_mapper.stop()

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