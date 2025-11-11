# File: core/app_modes.py

from enum import Enum

class AppMode(str, Enum):
    """
    Defines the distinct operational modes of the robot.
    Using an Enum makes state transitions safer and more readable.
    """
    OFF = "off"
    BOOTING = "booting"
    WORKING = "working"        # Idle, listening for commands
    COMPOSING = "composing"    # In a multi-step conversation to build a message
    SENDING = "sending"        # Physically moving to deliver a message
    RECEIVING = "receiving"    # At the destination, interacting with the recipient
    RETURNING = "returning"    # Physically moving back to the start point