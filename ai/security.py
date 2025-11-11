# File: ai/security.py

import logging
from typing import Optional, TYPE_CHECKING

# Avoid circular imports for type hinting
if TYPE_CHECKING:
    from robot.controller import RobotController

# Setup logger for this module
logger = logging.getLogger(__name__)


class SecurityManager:
    """
    Handles message protection: password verification and recipient identity checks.
    """

    def __init__(self, controller: 'RobotController'):
        """
        Initializes the security manager.
        
        Args:
            controller: The RobotController, needed for face recognition.
        """
        self.controller = controller

    def verify_password(self, spoken_password: str, correct_password: str) -> bool:
        """
        Checks if the spoken password matches the one stored in the message job.
        
        This is a simple, case-insensitive string comparison.
        """
        if not correct_password or not spoken_password:
            return False
            
        is_correct = spoken_password.lower().strip() == correct_password.lower().strip()
        
        if is_correct:
            logger.info("Password verification successful.")
        else:
            logger.warning(
                f"Password verification FAILED. "
                f"Spoken: '{spoken_password}', Expected: '{correct_password}'"
            )
        return is_correct

    async def verify_identity(self, expected_name: str, timeout: int = 15) -> bool:
        """
        Performs the "passport check" by verifying the recipient's identity.
        
        This uses the robot's camera to perform face recognition and
        compares the recognized name against the expected recipient's name.
        
        Args:
            expected_name: The recipient's name stored in the message job.
            timeout: How long to wait for a face to be recognized.
            
        Returns:
            True if the recognized face's name matches the expected name.
            False otherwise (or if no face is seen).
        """
        logger.info(f"Starting identity verification ('passport check') for: {expected_name}")
        
        # Use the controller's built-in face recognition method
        face_response = await self.controller.wait_for_face_recognition(timeout=timeout)
        
        if face_response is None:
            logger.warning("Identity check FAILED: No face was recognized in time.")
            return False
            
        # The SDK returns a list of faces; we check the first and most prominent one.
        recognized_name = face_response.faceInfos[0].name
        
        if recognized_name == "stranger":
            logger.warning(
                f"Identity check FAILED: A face was seen, but it was a 'stranger', "
                f"not '{expected_name}'."
            )
            return False
        
        # Compare the recognized name (case-insensitive)
        is_match = recognized_name.lower() == expected_name.lower()
        
        if is_match:
            logger.info(f"Identity check SUCCESS: Recognized '{recognized_name}' matches expected '{expected_name}'.")
        else:
            logger.warning(
                f"Identity check FAILED: Recognized name '{recognized_name}' "
                f"does NOT match expected '{expected_name}'."
            )
            
        return is_match