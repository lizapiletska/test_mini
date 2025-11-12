# File: vision/visual_mapper.py

import logging
import math
import queue
import threading
from typing import Optional, List, Tuple, Dict

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrow
from matplotlib.text import Text

from core.robot_state import RobotState 

logger = logging.getLogger(__name__)

BG_COLOR = "#F0F8FF"
GRID_COLOR = "#D3D3D3"
ROBOT_COLOR = "#00008B"
HEADING_COLOR = "#4169E1"
OBSTACLE_COLOR = "#FF0000"
# --- *** NEW *** ---
LOCATION_COLOR = "#0000FF" # Blue
LOCATION_MARKER = "X"

class VisualMapper:
    """
    Runs a Matplotlib 2D plot in a separate thread
    to visualize the robot's state and scan in real-time.
    """

    def __init__(self, robot_state: RobotState, map_size_meters=10):
        self.robot_state = robot_state
        self.map_size = map_size_meters
        self.plot_radius = math.ceil(self.map_size / 2.0)
        
        self.data_queue = queue.Queue()
        self.is_running = False
        self.thread = None

        self.fig = None
        self.ax = None
        self.robot_dot = None
        self.heading_arrow = None
        
        self.obstacle_markers: List[plt.Circle] = []
        self.obstacle_texts: List[Text] = []
        # --- *** NEW *** ---
        self.location_markers: List[plt.Line2D] = []
        self.location_texts: List[Text] = []

    def _plot_thread(self):
        """The main function for the plotting thread."""
        logger.info("VisualMapper thread started.")
        self.is_running = True
        plt.ion()

        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.fig.set_facecolor(BG_COLOR)
        self.ax.set_facecolor(BG_COLOR)
        
        self.ax.set_xlim(-self.plot_radius, self.plot_radius)
        self.ax.set_ylim(-self.plot_radius, self.plot_radius)
        self.ax.set_aspect('equal')
        self.ax.set_xlabel("Meters (X)")
        self.ax.set_ylabel("Meters (Y)")
        self.ax.set_title("Robot Live Map")
        self.ax.grid(True, color=GRID_COLOR, linestyle='--')

        x, y, heading = self.robot_state.get_state()
        self.robot_dot = self.ax.scatter(
            [x], [y], c=ROBOT_COLOR, s=150, zorder=5, label="Robot"
        )

        math_angle_rad = np.deg2rad(90 - heading)
        dx = 0.5 * np.cos(math_angle_rad)
        dy = 0.5 * np.sin(math_angle_rad)
        self.heading_arrow = FancyArrow(
            x, y, dx, dy,
            color=HEADING_COLOR, width=0.05, head_width=0.2, zorder=4
        )
        self.ax.add_patch(self.heading_arrow)
        self.ax.legend(loc="upper right")
        
        self.fig.canvas.draw_idle()
        plt.pause(0.1)

        while self.is_running:
            try:
                event_type, data = self.data_queue.get(timeout=0.05)
                
                if event_type == "STOP":
                    self.is_running = False
                    continue

                elif event_type == "UPDATE_STATE":
                    x, y, heading = data
                    self.robot_dot.set_offsets([x, y])
                    self.heading_arrow.remove()
                    math_angle_rad = np.deg2rad(90 - heading)
                    dx = 0.5 * np.cos(math_angle_rad)
                    dy = 0.5 * np.sin(math_angle_rad)
                    self.heading_arrow = FancyArrow(
                        x, y, dx, dy,
                        color=HEADING_COLOR, width=0.05, head_width=0.2, zorder=4
                    )
                    self.ax.add_patch(self.heading_arrow)
                    self.ax.draw_artist(self.robot_dot)
                    self.ax.draw_artist(self.heading_arrow)

                elif event_type == "ADD_OBSTACLE":
                    x, y, label = data
                    self._draw_obstacle(x, y, label)

                elif event_type == "LOAD_OBSTACLES":
                    map_data_list = data
                    logger.info(f"Visualizer loading {len(map_data_list)} obstacles from map file...")
                    for point in map_data_list:
                        angle_deg = point.get('angle', 0)
                        dist_mm = point.get('distance_mm')
                        
                        if dist_mm is not None:
                            label = f"{dist_mm}mm"
                            math_angle_rad = np.deg2rad(90 - angle_deg)
                            dist_m = dist_mm / 1000.0
                            x = dist_m * np.cos(math_angle_rad)
                            y = dist_m * np.sin(math_angle_rad)
                            self._draw_obstacle(x, y, label)
                
                # --- *** NEW *** ---
                elif event_type == "ADD_LOCATION":
                    x, y, label = data
                    self._draw_location(x, y, label)

                # --- *** NEW *** ---
                elif event_type == "LOAD_LOCATIONS":
                    locations_list = data
                    logger.info(f"Visualizer loading {len(locations_list)} saved locations...")
                    for loc in locations_list:
                        name = loc.get("name")
                        x = loc.get("location", {}).get("x")
                        y = loc.get("location", {}).get("y")
                        if name and x is not None and y is not None:
                            self._draw_location(x, y, name)
                
                self.fig.canvas.flush_events()
                
            except queue.Empty:
                plt.pause(0.05) # <-- The anti-lag fix
                
            except Exception as e:
                logger.error(f"Error in visual mapper thread: {e}")
                self.is_running = False

        plt.ioff()
        plt.close(self.fig)
        logger.info("VisualMapper thread stopped.")

    def _draw_obstacle(self, x: float, y: float, label: str):
        """Helper function to draw a single obstacle."""
        obstacle_marker = plt.Circle(
            (x, y), 0.1,
            facecolor='none',
            edgecolor=OBSTACLE_COLOR,
            linewidth=2,
            zorder=3
        )
        obstacle_text = self.ax.text(
            x, y, label,
            fontsize='small',
            color='black',
            ha='center',
            va='center',
            zorder=3
        )
        self.ax.add_patch(obstacle_marker)
        self.obstacle_markers.append(obstacle_marker)
        self.obstacle_texts.append(obstacle_text)
        self.ax.draw_artist(obstacle_marker)
        self.ax.draw_artist(obstacle_text)

    # --- *** NEW *** ---
    def _draw_location(self, x: float, y: float, label: str):
        """Helper function to draw a single permanent location."""
        # Plot a blue 'X'
        loc_marker, = self.ax.plot(
            x, y,
            marker=LOCATION_MARKER,
            color=LOCATION_COLOR,
            markersize=10,
            linestyle='none',
            zorder=2
        )
        # Add a blue label
        loc_text = self.ax.text(
            x, y + 0.15, label, # Place text slightly above marker
            fontsize='medium',
            color=LOCATION_COLOR,
            ha='center',
            va='bottom',
            zorder=2
        )
        self.location_markers.append(loc_marker)
        self.location_texts.append(loc_text)
        self.ax.draw_artist(loc_marker)
        self.ax.draw_artist(loc_text)

    # --- Thread-Safe Public Methods ---

    def update_robot_state(self, x: float, y: float, heading: float):
        if self.is_running:
            self.data_queue.put(("UPDATE_STATE", (x, y, heading)))

    def add_obstacle(self, x: float, y: float, label: str):
        if self.is_running:
            self.data_queue.put(("ADD_OBSTACLE", (x, y, label)))

    def load_obstacles(self, map_data: List[Dict]):
        if self.is_running and map_data:
            self.data_queue.put(("LOAD_OBSTACLES", map_data))

    # --- *** NEW *** ---
    def add_permanent_location(self, x: float, y: float, label: str):
        """Thread-safe method to add a new saved location to the plot."""
        if self.is_running:
            self.data_queue.put(("ADD_LOCATION", (x, y, label)))
            
    # --- *** NEW *** ---
    def load_permanent_locations(self, locations_list: List[Dict]):
        """Thread-safe method to batch-load saved locations."""
        if self.is_running and locations_list:
            self.data_queue.put(("LOAD_LOCATIONS", locations_list))

    def start(self):
        if not self.is_running:
            self.thread = threading.Thread(target=self._plot_thread, daemon=True)
            self.thread.start()

    def stop(self):
        if self.is_running:
            self.data_queue.put(("STOP", None))
            self.thread.join(timeout=1.0)
            self.is_running = False