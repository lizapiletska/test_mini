import logging
from mini.mini_sdk import RobotType  # Import RobotType from the SDK

# === Robot Connection Settings ===
ROBOT_IP: str = "192.168.137.7"  # The IP address you provided
ROBOT_PORT: int = 8800
ROBOT_TYPE: RobotType = RobotType.EDU  # Use the enum from the SDK
LOG_LEVEL: int = logging.INFO

# Time to wait after entering programming mode for the robot to be ready
PROGRAM_MODE_WAIT_TIME_SEC: int = 3

# === AI Model Configuration ===
# Assumes Ollama is running locally.
# See: https://github.com/ollama/ollama-python
OLLAMA_HOST: str = "http://127.0.0.1:11434"
OLLAMA_MODEL: str = "mistral"  # The model you mentioned

# Confidence threshold for AI to "understand" an intent
AI_CONFIDENCE_THRESHOLD: float = 0.75

# === Application Logic Settings ===
# From your "Receiving" state requirements
LISTEN_TIMEOUT_SECONDS: int = 30
LISTEN_RETRY_ATTEMPTS: int = 5

# === Sensor & Navigation Settings ===
# Max distance (in mm) before an obstacle is considered "blocking"
# From SDK docs, GetInfraredDistance seems to use mm
OBSTACLE_THRESHOLD_MM: int = 300  # 30 cm

# === Data Storage Paths ===
MAP_FILE_PATH: str = "data/maps/main_room_map.json"
ROUTES_DIRECTORY: str = "data/routes/"
PROFILES_DIRECTORY: str = "data/profiles/"
# --- *** MODIFIED *** ---
# This is now a directory to store all individual message logs
MESSAGES_DIRECTORY: str = "data/messages/"