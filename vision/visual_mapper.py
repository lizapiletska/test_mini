# File: vision/visual_mapper.py

import logging
import math
import queue
import threading
from typing import Optional, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrow
from matplotlib.text import Text

# Avoid circular import
from core.robot_state import RobotState 

logger = logging.getLogger(__name__)

# Define our plot colors
BG_COLOR = "#F0F8FF"  # AliceBlue (light blue/white)
GRID_COLOR = "#D3D3D3" # LightGray
ROBOT_COLOR = "#00008B" # DarkBlue
HEADING_COLOR = "#4169E1" # RoyalBlue
OBSTACLE_COLOR = "#FF0000" # Red

class VisualMapper:
    """
    Runs a Matplotlib 2D plot in a separate thread
    to visualize the robot's state and scan in real-time.
    """

    def __init__(self, robot_state: RobotState, map_size_meters=10):
        self.robot_state = robot_state
        self.map_size = map_size_meters
        self.plot_radius = math.ceil(self.map_size / 2.0)
        
        # Use a queue for thread-safe communication
        self.data_queue = queue.Queue()
        self.is_running = False
        self.thread = None

        # Matplotlib object references
        self.fig = None
        self.ax = None
        self.robot_dot = None
        self.heading_arrow = None
        
        # --- MODIFIED ---
        # Keep track of obstacle markers and text
        self.obstacle_markers: List[plt.Circle] = []
        self.obstacle_texts: List[Text] = []

    def _plot_thread(self):
        """The main function for the plotting thread."""
        logger.info("VisualMapper thread started.")
        self.is_running = True
        plt.ion()

        # 1. Initialize the Plot
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

        # 2. Draw the Robot at its initial state
        x, y, heading = self.robot_state.get_state()
        self.robot_dot = self.ax.scatter(
            [x], [y], c=ROBOT_COLOR, s=150, zorder=5, label="Robot"
        )

        # 3. Draw the initial heading
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

        # 4. Main plotting loop
        while self.is_running:
            try:
                # Wait for new data from the main thread
                event_type, data = self.data_queue.get(timeout=0.1)
                
                if event_type == "STOP":
                    self.is_running = False
                    continue

                elif event_type == "UPDATE_STATE":
                    x, y, heading = data
                    
                    # Update robot position
                    self.robot_dot.set_offsets([x, y])
                    
                    # Update heading arrow
                    self.heading_arrow.remove() # Remove old arrow
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
                    
                    # Draw a hollow red circle
                    obstacle_marker = plt.Circle(
                        (x, y), 0.1, # 10cm radius
                        facecolor='none',
                        edgecolor=OBSTACLE_COLOR,
                        linewidth=2,
                        zorder=3
                    )
                    # Add the distance text
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

                # Redraw canvas
                self.fig.canvas.flush_events()
                
            except queue.Empty:
                pass # This is normal
            except Exception as e:
                logger.error(f"Error in visual mapper thread: {e}")
                self.is_running = False

        plt.ioff()
        plt.close(self.fig)
        logger.info("VisualMapper thread stopped.")

    # --- Thread-Safe Public Methods ---

    def update_robot_state(self, x: float, y: float, heading: float):
        """Called by the MovementController to update the robot's position."""
        if self.is_running:
            self.data_queue.put(("UPDATE_STATE", (x, y, heading)))

    def add_obstacle(self, x: float, y: float, label: str):
        """Called by the Mapper to add a new obstacle to the plot."""
        if self.is_running:
            self.data_queue.put(("ADD_OBSTACLE", (x, y, label)))

    def start(self):
        """Starts the plotting thread."""
        if not self.is_running:
            self.thread = threading.Thread(target=self._plot_thread, daemon=True)
            self.thread.start()

    def stop(self):
        """Stops the plotting thread."""
        if self.is_running:
            self.data_queue.put(("STOP", None))
            self.thread.join(timeout=1.0)
            self.is_running = False