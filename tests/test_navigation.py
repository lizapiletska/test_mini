# File: tests/test_navigation.py

import unittest
from robot.navigation.planner import Planner
from mini.apis.api_action import MoveRobotDirection

class TestNavigationPlanner(unittest.TestCase):

    def setUp(self):
        # Create a new planner instance for each test
        self.planner = Planner()

    def test_parse_simple_forward(self):
        """Tests a simple forward command."""
        text = "50 steps forward"
        expected_route = [(MoveRobotDirection.FORWARD, 50)]
        
        route = self.planner.parse_address_to_route(text)
        self.assertEqual(route, expected_route)

    def test_parse_complex_route(self):
        """Tests a multi-step command with different keywords."""
        text = "go 20 left and then 10 steps back, then turn 5 rightward"
        expected_route = [
            (MoveRobotDirection.LEFTWARD, 20),
            (MoveRobotDirection.BACKWARD, 10),
            (MoveRobotDirection.RIGHTWARD, 5)
        ]
        
        route = self.planner.parse_address_to_route(text)
        self.assertEqual(route, expected_route)

    def test_parse_invalid_text(self):
        """Tests that non-address text returns None."""
        text = "hello, how are you?"
        route = self.planner.parse_address_to_route(text)
        self.assertIsNone(route)

    def test_parse_no_number(self):
        """Tests that a command with no number is ignored."""
        text = "go forward and then 15 left"
        expected_route = [(MoveRobotDirection.LEFTWARD, 15)]
        
        route = self.planner.parse_address_to_route(text)
        self.assertEqual(route, expected_route)

if __name__ == '__main__':
    unittest.main()