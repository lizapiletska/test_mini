# File: core/state_manager.py

import asyncio
from typing import TYPE_CHECKING, Optional, Any

from core.context import get_state, set_state

# This avoids circular import errors, allowing type hinting
# for classes that are not yet fully defined.
if TYPE_CHECKING:
    from robot.controller import RobotController
    from ai.orchestrator import AIOrchestrator


class StateManager:
    """
    Provides "guarded" functions for all major robot actions.
    
    These methods wrap the raw robot/AI calls, ensuring that:
    1. The action is allowed according to the current state (e.g., "don't listen while speaking").
    2. The state is correctly set during the action (e.g., `isSpeaking = True`).
    3. The state is reset after the action completes.
    
    All other application logic (like in `main.py` or `ai/orchestrator.py`)
    should use these StateManager methods instead of calling the
    robot controller or AI directly.
    """

    def __init__(self, robot_controller: 'RobotController', ai_orchestrator: 'AIOrchestrator'):
        self.robot = robot_controller
        self.ai = ai_orchestrator

    async def safe_say(self, text: str) -> bool:
        """
        Guarded TTS function.
        Will not speak if the robot is currently listening.
        """
        state = get_state()
        
        # Your rule: "check if the current mode is not 'Listening'"
        if state["isListening"]:
            print(f"STATE_GUARD: Blocked 'say' because robot is listening.")
            return False

        # Your rule: "set the isSpeaking true ad false by itlef"
        set_state(isSpeaking=True)
        try:
            # The actual robot call is delegated to the controller
            await self.robot.speak(text)
            return True
        except Exception as e:
            print(f"ERROR in safe_say: {e}")
            return False
        finally:
            set_state(isSpeaking=False)

    async def safe_listen(self) -> Optional[str]:
        """
        Guarded ASR/Listening function.
        Will not listen if the robot is busy (speaking, walking, or analyzing).
        """
        state = get_state()
        
        # Your rule: "check if not speaking or not walking... also do not listen while the isAiAnalyzing is true"
        if state["isSpeaking"] or state["isWalking"] or state["isAiAnalyzing"]:
            print(f"STATE_GUARD: Blocked 'listen' because robot is busy.")
            return None
        
        # Your rule: "chang the golbal states of isLiestening"
        set_state(isListening=True)
        try:
            # The robot controller will handle the complexity of
            # starting the 'ObserveSpeechRecognise' SDK event listener
            # and returning a single string result.
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
        Ensures only one analysis task runs at a time.
        """
        state = get_state()
        
        if state["isAiAnalyzing"]:
            print(f"STATE_GUARD: Blocked 'analyze' because AI is already working.")
            return None
            
        set_state(isAiAnalyzing=True)
        try:
            # The AI orchestrator will take the text, call Ollama,
            # and return a structured response (e.g., an intent object).
            ai_response = await self.ai.process_text(text)
            return ai_response
        except Exception as e:
            print(f"ERROR in safe_analyze_ai: {e}")
            return None
        finally:
            set_state(isAiAnalyzing=False)

    # --- 'safe_walk' method has been removed ---
    # The logic is now handled by 'safe_execute_route' in main.py,
    # which is more comprehensive as it includes obstacle detection.