import asyncio
from typing import TYPE_CHECKING, Optional, Any

from core.context import get_state, set_state

# This avoids circular import errors, allowing type hinting
if TYPE_CHECKING:
    from robot.controller import RobotController
    from ai.orchestrator import AIOrchestrator
    # --- *** NEW *** ---
    from ai.memory import MemoryManager


class StateManager:
    """
    Provides "guarded" functions for all major robot actions.
    ...
    """

    # --- *** MODIFIED *** ---
    def __init__(self, 
                 robot_controller: 'RobotController', 
                 ai_orchestrator: 'AIOrchestrator',
                 memory_manager: 'MemoryManager'): # <-- Added
        self.robot = robot_controller
        self.ai = ai_orchestrator
        # --- *** NEW *** ---
        self.memory = memory_manager

    async def safe_say(self, text: str) -> bool:
        """
        Guarded TTS function.
        Will not speak if the robot is currently listening.
        --- *** NEW: Now also logs the robot's speech. *** ---
        """
        state = get_state()
        
        if state["isListening"]:
            print(f"STATE_GUARD: Blocked 'say' because robot is listening.")
            return False

        set_state(isSpeaking=True)
        try:
            # The actual robot call is delegated to the controller
            await self.robot.speak(text)
            
            # --- *** NEW *** ---
            # Log the exchange *after* it was successfully spoken
            self.memory.log_exchange("robot", text)
            
            return True
        except Exception as e:
            print(f"ERROR in safe_say: {e}")
            return False
        finally:
            set_state(isSpeaking=False)

    async def safe_listen(self) -> Optional[str]:
        """
        Guarded ASR/Listening function.
        (Function unchanged)
        """
        state = get_state()
        
        if state["isSpeaking"] or state["isWalking"] or state["isAiAnalyzing"]:
            print(f"STATE_GUARD: Blocked 'listen' because robot is busy.")
            return None
        
        set_state(isListening=True)
        try:
            text_result = await self.robot.listen_for_speech()
            return text_result
        except Exception as e:
            print(f"ERROR in safe_listen: {e}")
            return None
        finally:
            set_state(isListening=False)

    async def safe_analyze_ai(self, text: str) -> Optional[Any]:
        """
        Guarded AI analysis function.
        (Function unchanged)
        """
        state = get_state()
        
        if state["isAiAnalyzing"]:
            print(f"STATE_GUARD: Blocked 'analyze' because AI is already working.")
            return None
            
        set_state(isAiAnalyzing=True)
        try:
            ai_response = await self.ai.process_text(text)
            return ai_response
        except Exception as e:
            print(f"ERROR in safe_analyze_ai: {e}")
            return None
        finally:
            set_state(isAiAnalyzing=False)