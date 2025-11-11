# File: tests/test_ai_orchestrator.py

import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from ai.orchestrator import AIOrchestrator

# This helper class is needed because 'unittest.mock' doesn't
# fully support mocking async classes out of the box.
class MockOllamaClient:
    def __init__(self):
        # The 'chat' method is the one we need to mock
        self.chat = AsyncMock()
    
    def list(self):
        # Mock the 'list' method called in the constructor
        return True

class TestAIOrchestrator(unittest.TestCase):

    def setUp(self):
        # Create a patch for the 'ollama.Client'
        self.ollama_patcher = patch('ai.orchestrator.ollama.Client', new_callable=MockOllamaClient)
        self.mock_ollama_client = self.ollama_patcher.start()
        
        # Instantiate our orchestrator. It will now use the MOCK client.
        self.orchestrator = AIOrchestrator()

    def tearDown(self):
        # Stop the patcher to clean up
        self.ollama_patcher.stop()

    def test_process_send_intent(self):
        """Tests if the orchestrator correctly parses a SEND_MESSAGE intent."""
        
        # 1. Define the FAKE response from the AI
        ai_response_json = """
        {
            "intent": "SEND_MESSAGE",
            "recipient_name": "Person B"
        }
        """
        mock_response = {'message': {'content': ai_response_json}}
        self.mock_ollama_client.chat.return_value = mock_response
        
        # 2. Run the text through our orchestrator
        text = "robot, send a message to Person B"
        result = asyncio.run(self.orchestrator.process_text(text))
        
        # 3. Check the results
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], "SEND_MESSAGE")
        self.assertEqual(result['recipient_name'], "Person B")

    def test_process_address_intent(self):
        """Tests if the orchestrator correctly parses an address."""
        
        # 1. Define the FAKE response
        ai_response_json = """
        {
            "intent": "PROVIDE_ADDRESS",
            "address_text": "50 steps forward turn 90 left"
        }
        """
        mock_response = {'message': {'content': ai_response_json}}
        self.mock_ollama_client.chat.return_value = mock_response
        
        # 2. Run the text
        text = "50 steps forward turn 90 left"
        result = asyncio.run(self.orchestrator.process_text(text))
        
        # 3. Check the results
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], "PROVIDE_ADDRESS")
        self.assertEqual(result['address_text'], "50 steps forward turn 90 left")

    def test_ai_returns_bad_json(self):
        """Tests that our code returns None if the AI hallucinates bad JSON."""
        
        # 1. Define FAKE bad response
        ai_response_bad_json = """
        {
            "intent": "PROVIDE_ADDRESS",
            "address_text": "50 steps forward" 
        """ # <--- Missing closing brace
        mock_response = {'message': {'content': ai_response_bad_json}}
        self.mock_ollama_client.chat.return_value = mock_response
        
        # 2. Run the text
        text = "50 steps"
        result = asyncio.run(self.orchestrator.process_text(text))
        
        # 3. Check that our orchestrator handled the error
        self.assertIsNone(result)