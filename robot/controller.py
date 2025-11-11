# File: robot/controller.py

import asyncio
import logging
from typing import Optional, List, Tuple, Any

# --- Core SDK Imports ---
from mini import mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_setup import StartRunProgram, StopRunProgram

# --- Settings ---
from config import settings

# --- Voice API Imports ---
from mini.apis.api_sound import StartPlayTTS, StopAllAudio
from mini.apis.api_observe import ObserveSpeechRecognise
from mini.pb2.codemao_speechrecognise_pb2 import SpeechRecogniseResponse

# --- Sensor API Imports ---
from mini.apis.api_sence import GetInfraredDistance
from mini.pb2.codemao_getinfrareddistance_pb2 import GetInfraredDistanceResponse

# --- Vision API Imports ---
from mini.apis.api_observe import ObserveFaceRecognise, ObserveFaceDetect
from mini.pb2.codemao_facerecognisetask_pb2 import FaceRecogniseTaskResponse
from mini.pb2.codemao_facedetecttask_pb2 import FaceDetectTaskResponse

# --- Movement API Imports ---
from mini.apis.api_action import MoveRobot, MoveRobotDirection

# Setup logger for this module
logger = logging.getLogger(__name__)


class RobotController:
    """
    Hardware Abstraction Layer for the Alpha Mini Robot.
    
    This class wraps all low-level MiniSdk calls into clean,
    async/await methods for use by the StateManager and other
    application components.
    """
    def __init__(self):
        self.device: Optional[WiFiDevice] = None
        self._speech_observer: Optional[ObserveSpeechRecognise] = None
        self._face_rec_observer: Optional[ObserveFaceRecognise] = None
        self._face_detect_observer: Optional[ObserveFaceDetect] = None

    async def connect(self) -> bool:
        """
        Initializes the SDK and connects to the robot at the IP in settings.
        Enters programming mode.
        """
        logger.info(f"Initializing SDK for RobotType: {settings.ROBOT_TYPE.name}")
        MiniSdk.set_log_level(settings.LOG_LEVEL)
        MiniSdk.set_robot_type(settings.ROBOT_TYPE)

        # Connect directly using the IP and Port from settings
        self.device = WiFiDevice(address=settings.ROBOT_IP, port=settings.ROBOT_PORT, name="PostmanRobot")
        logger.info(f"Attempting connection to {settings.ROBOT_IP}:{settings.ROBOT_PORT}...")

        try:
            connected: bool = await MiniSdk.connect(self.device)
            if not connected:
                logger.error(f"Connection failed: Could not connect to {settings.ROBOT_IP}.")
                self.device = None
                return False

            logger.info("Connection successful. Entering programming mode...")
            (result, response) = await StartRunProgram().execute()
            
            if not response or not response.isSuccess:
                logger.error(f"Failed to enter programming mode. Result: {response}")
                await MiniSdk.release()
                return False

            await asyncio.sleep(settings.PROGRAM_MODE_WAIT_TIME_SEC)
            logger.info("Robot is connected and in programming mode. Ready.")
            return True

        except Exception as e:
            logger.error(f"An exception occurred during connection: {e}")
            self.device = None
            return False

    async def disconnect(self):
        """
        Exits programming mode and releases all SDK resources.
        """
        if self.device:
            try:
                logger.info("Exiting programming mode...")
                await StopRunProgram().execute()
            except Exception as e:
                logger.warning(f"Error quitting program mode: {e}")
            
            try:
                logger.info("Releasing SDK resources...")
                await MiniSdk.release()
            except Exception as e:
                logger.warning(f"Error releasing SDK: {e}")
                
            self.device = None
            logger.info("Robot disconnected.")

    # ----------------------------------------
    # --- Voice Methods
    # ----------------------------------------

    async def speak(self, text: str) -> bool:
        """
        Uses the SDK's TTS to make the robot speak.
        """
        if not self.device:
            logger.warning("Speak failed: Robot not connected.")
            return False
            
        logger.info(f"Robot speaking: '{text}'")
        try:
            # Ensure no other audio is playing
            await StopAllAudio().execute()
            
            block = StartPlayTTS(text=text)
            (result_type, response) = await block.execute()

            if response and response.isSuccess:
                return True
            else:
                logger.error(f"TTS failed: {response}")
                return False
        except Exception as e:
            logger.error(f"Exception during speak: {e}")
            return False

    async def listen_for_speech(self, timeout: int = 10) -> Optional[str]:
        """
        Listens for a single speech utterance.
        
        This method converts the SDK's callback-based 'ObserveSpeechRecognise'
        into a clean async/await function using asyncio.Future.
        """
        if self._speech_observer:
            logger.warning("Speech observer already active.")
            return None
            
        future = asyncio.Future()
        self._speech_observer = ObserveSpeechRecognise()

        def handler(msg: SpeechRecogniseResponse):
            logger.debug(f"Speech handler received: {msg.text}")
            if msg.isSuccess and msg.text and not future.done():
                self._speech_observer.stop()
                future.set_result(msg.text)
            elif not msg.isSuccess and not future.done():
                future.set_exception(Exception(f"ASR Error: {msg.resultCode}"))

        self._speech_observer.set_handler(handler)
        self._speech_observer.start()
        logger.info("Speech listener started. Waiting for utterance...")

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Speech recognition timed out after {timeout}s.")
            self._speech_observer.stop()
            return None
        except Exception as e:
            logger.error(f"Speech recognition error: {e}")
            return None
        finally:
            self._speech_observer = None

    # ----------------------------------------
    # --- Movement & Sensor Methods
    # ----------------------------------------

    async def move(self, direction: MoveRobotDirection, steps: int = 1) -> bool:
        """
        Executes a single, basic movement command.
        """
        logger.info(f"Moving {direction.name} for {steps} steps.")
        block = MoveRobot(direction=direction, step=steps)
        (_, response) = await block.execute()
        
        if not response or not response.isSuccess:
            logger.error(f"Movement failed: {response}")
            return False
        return True

    async def get_infrared_distance(self) -> Optional[int]:
        """
        Gets a one-time reading from the front infrared sensor.
        Returns distance in millimeters.
        """
        block = GetInfraredDistance()
        (_, response) = await block.execute()
        
        if response and response.distance > 0:
            logger.debug(f"Infrared distance: {response.distance}mm")
            return response.distance
        else:
            logger.warning(f"Failed to read infrared sensor: {response}")
            return None

    # ----------------------------------------
    # --- Vision Methods
    # ----------------------------------------

    async def wait_for_face_recognition(self, timeout: int = 10) -> Optional[FaceRecogniseTaskResponse]:
        """
        Waits for a face to be recognized (stranger or known).
        
        Used for the "passport" check. Returns the full response object.
        """
        if self._face_rec_observer:
            logger.warning("Face recognition observer already active.")
            return None

        future = asyncio.Future()
        self._face_rec_observer = ObserveFaceRecognise()

        def handler(msg: FaceRecogniseTaskResponse):
            logger.debug(f"Face recognition handler received: {msg}")
            if msg.isSuccess and msg.faceInfos and not future.done():
                self._face_rec_observer.stop()
                future.set_result(msg)
            elif not msg.isSuccess and not future.done():
                future.set_exception(Exception(f"Face Rec Error: {msg.resultCode}"))

        self._face_rec_observer.set_handler(handler)
        self._face_rec_observer.start()
        logger.info("Face recognition listener started. Waiting for face...")

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Face recognition timed out after {timeout}s.")
            self._face_rec_observer.stop()
            return None
        except Exception as e:
            logger.error(f"Face recognition error: {e}")
            return None
        finally:
            self._face_rec_observer = None