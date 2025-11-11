# File: tests/test_state_manager.py

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from core.state_manager import StateManager
from core.context import set_state, get_state, STATE_VARS, _mode
from core.app_modes import AppMode

class TestStateManager(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # 1. Create mock (fake) versions of the dependencies
        self.mock_robot_controller = MagicMock()
        self.mock_robot_controller.speak = AsyncMock(return_value=True)
        self.mock_robot_controller.listen_for_speech = AsyncMock(return_value="hello")
        
        self.mock_ai_orchestrator = MagicMock()
        self.mock_ai_orchestrator.process_text = AsyncMock(return_value={"intent": "FRIENDLY_CHAT"})

        # 2. Initialize the StateManager with the mocks
        self.state_manager = StateManager(
            robot_controller=self.mock_robot_controller,
            ai_orchestrator=self.mock_ai_orchestrator
        )
        
        # 3. Reset all context variables before each test
        for var in STATE_VARS.values():
            var.set(var.default)

    async def test_safe_say_happy_path(self):
        """Tests that safe_say calls the robot and updates state."""
        
        # Ensure we are not listening
        set_state(isListening=False)
        
        await self.state_manager.safe_say("test text")
        
        # Check that the robot's "speak" method was called
        self.mock_robot_controller.speak.assert_called_once_with("test text")
        
        # Check that the state was correctly set back to False
        self.assertEqual(get_state()['isSpeaking'], False)

    async def test_guard_say_is_blocked_by_listen(self):
        """Tests the guard: safe_say should NOT run if isListening is True."""
        
        # Set the blocking state
        set_state(isListening=True)
        
        result = await self.state_manager.safe_say("test text")
        
        # Check that the function returned False (blocked)
        self.assertEqual(result, False)
        
        # Check that the robot's "speak" method was NEVER called
        self.mock_robot_controller.speak.assert_not_called()

    async def test_guard_listen_is_blocked_by_speaking(self):
        """Tests the guard: safe_listen should NOT run if isSpeaking is True."""
        
        # Set the blocking state
        set_state(isSpeaking=True)
        
        result = await self.state_manager.safe_listen()
        
        # Check that the function returned None (blocked)
        self.assertIsNone(result)
        
        # Check that the robot's "listen" method was NEVER called
        self.mock_robot_controller.listen_for_speech.assert_not_called()

    async def test_guard_listen_is_blocked_by_walking(self):
        """Tests the guard: safe_listen should NOT run if isWalking is True."""
        
        # Set the blocking state
        set_state(isWalking=True)
        
        result = await self.state_manager.safe_listen()
        
        # Check that the function returned None (blocked)
        self.assertIsNone(result)
        
        # Check that the robot's "listen" method was NEVER called
        self.mock_robot_controller.listen_for_speech.assert_not_called()