# File: vision/visual_mapper.py

import logging
import math
import queue
import threading
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrow

logger = logging.getLogger(__name__)

# Define our plot colors
BG_COLOR = "#F0F8FF"  # AliceBlue (light blue/white)
GRID_COLOR = "#D3D3D3" # LightGray
ROBOT_COLOR = "#00008B" # DarkBlue
HEADING_COLOR = "#4169E1" # RoyalBlue
OBSTACLE_COLOR = "#FF0000" # Red

class VisualMapper:
    """
    Runs a Matplotlib 2D polar plot in a separate thread
    to visualize the robot's room scan in real-time.
    """

    def __init__(self, map_size_meters=10):
        self.map_size = map_size_meters
        self.plot_radius = math.ceil(self.map_size / 2.0)
        self.data_queue = queue.Queue()
        self.is_running = False
        self.thread = None

        self.fig = None
        self.ax = None
        self.robot_dot = None
        self.heading_arrow = None
        self.obstacle_scatter = None
        self.scan_points = []

    def _plot_thread(self):
        """The main function for the plotting thread."""
        logger.info("VisualMapper thread started.")
        self.is_running = True

        # Enable interactive mode
        plt.ion()

        # 1. Initialize the Plot
        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.fig.set_facecolor(BG_COLOR)
        self.ax.set_facecolor(BG_COLOR)
        
        # Set up the 10x10 meter square
        self.ax.set_xlim(-self.plot_radius, self.plot_radius)
        self.ax.set_ylim(-self.plot_radius, self.plot_radius)
        self.ax.set_aspect('equal')
        self.ax.set_xlabel("Meters (X)")
        self.ax.set_ylabel("Meters (Y)")
        self.ax.set_title("Robot Live Scan")
        self.ax.grid(True, color=GRID_COLOR, linestyle='--')

        # 2. Draw the Robot at the center (0, 0)
        self.robot_dot = self.ax.scatter(
            [0], [0], c=ROBOT_COLOR, s=150, zorder=5, label="Robot"
        )

        # 3. Draw the initial heading (0 degrees, "north")
        self.heading_arrow = FancyArrow(
            0, 0, 0, 0.5, # x, y, dx, dy
            color=HEADING_COLOR,
            width=0.05,
            head_width=0.2,
            zorder=4
        )
        self.ax.add_patch(self.heading_arrow)

        # 4. Prepare the obstacle scatter plot
        # We plot empty data initially and will update it
        self.obstacle_scatter = self.ax.scatter(
            [], [], c=OBSTACLE_COLOR, s=50, zorder=3, label="Obstacles"
        )
        
        self.ax.legend(loc="upper right")
        self.fig.canvas.draw_idle()
        plt.pause(0.1)

        # 5. Main plotting loop
        while self.is_running:
            try:
                # Wait for new data from the main thread
                # This blocks the *plotting thread* (not the main app)
                # until new data arrives.
                data = self.data_queue.get(timeout=0.1)
                
                if data == "STOP":
                    self.is_running = False
                    continue

                # Unpack data
                angle_deg, dist_mm, heading_deg = data
                
                # --- Update Obstacles ---
                if dist_mm is not None:
                    # Convert polar (angle, dist) to cartesian (x, y)
                    # Note: 0-degrees is "North" (Y-axis) in robot-land,
                    # but "East" (X-axis) in math-land. We adjust.
                    # We also convert mm to meters.
                    
                    # Convert robot's angle (0=forward) to math angle (0=right)
                    math_angle_rad = np.deg2rad(90 - angle_deg)
                    dist_m = dist_mm / 1000.0
                    
                    x = dist_m * np.cos(math_angle_rad)
                    y = dist_m * np.sin(math_angle_rad)
                    
                    self.scan_points.append((x, y))
                    
                    # Update the scatter plot data
                    sc_data = np.array(self.scan_points)
                    self.obstacle_scatter.set_offsets(sc_data)
                
                # --- Update Robot Heading ---
                # Convert heading to dx, dy for the arrow
                heading_math_rad = np.deg2rad(90 - heading_deg)
                dx = 0.5 * np.cos(heading_math_rad)
                dy = 0.5 * np.sin(heading_math_rad)
                
                self.heading_arrow.set_data(dx=dx, dy=dy)
                
                # Redraw the canvas
                self.ax.draw_artist(self.heading_arrow)
                self.ax.draw_artist(self.obstacle_scatter)
                self.fig.canvas.flush_events()
                
            except queue.Empty:
                # This is normal, just means no new data
                pass
            except Exception as e:
                logger.error(f"Error in visual mapper thread: {e}")
                self.is_running = False

        # Close the plot
        plt.ioff()
        plt.close(self.fig)
        logger.info("VisualMapper thread stopped.")

    def update_map(self, angle_deg: float, dist_mm: Optional[int], heading_deg: float):
        """
        Thread-safe method called by the main asyncio loop to
        add new data to the plot.
        """
        if self.is_running:
            self.data_queue.put((angle_deg, dist_mm, heading_deg))

    def start(self):
        """Starts the plotting thread."""
        if not self.is_running:
            self.thread = threading.Thread(target=self._plot_thread, daemon=True)
            self.thread.start()

    def stop(self):
        """Stops the plotting thread."""
        if self.is_running:
            self.data_queue.put("STOP")
            self.thread.join(timeout=1.0)
            self.is_running = False