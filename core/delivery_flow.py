# File: core/delivery_flow.py

import asyncio
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from ai.memory import MemoryManager
from ai.security import SecurityManager
from config import prompts
from core.app_modes import AppMode
from core.context import set_state
from core.state_manager import StateManager
from robot.movement.route_recorder import RouteRecorder
from robot.navigation.planner import Planner, RoutePlan
from robot.navigation.obstacle_detector import ObstacleDetector
from mini.apis.api_action import MoveRobotDirection

# Import for type hinting
if TYPE_CHECKING:
    from core.movement_controller import MovementController
    from vision.visual_mapper import VisualMapper
    from core.robot_state import RobotState

logger = logging.getLogger(__name__)

class DeliveryFlow:
    def __init__(self,
                 state_manager: StateManager,
                 memory: MemoryManager,
                 planner: Planner,
                 security: SecurityManager,
                 recorder: RouteRecorder,
                 detector: ObstacleDetector,
                 movement_controller: 'MovementController',
                 robot_state: 'RobotState',
                 visual_mapper: 'VisualMapper'):
        
        self.state_manager = state_manager
        self.memory = memory
        self.planner = planner
        self.security = security
        self.recorder = recorder
        self.detector = detector
        self.movement_controller = movement_controller
        self.robot_state = robot_state
        self.visual_mapper = visual_mapper

    async def get_route_for_job(self, job: Dict[str, Any]) -> Optional[RoutePlan]:
        """
        Gets a route for a job, either from memory or by
        parsing the new AI-generated route_plan.
        """
        recipient_name = job['recipient_name']
        known_route = self.memory.get_known_route_for_recipient(recipient_name)
        
        if known_route:
            # This logic remains the same
            await self.state_manager.safe_say(prompts.RETURN_TO_SENDER_CONFIRM_ADDRESS.format(recipient_name))
            text = await self.state_manager.safe_listen()
            self.memory.log_exchange("user", text) 
            
            if text:
                ai_data = await self.state_manager.safe_analyze_ai(text)
                if ai_data and ai_data.get('intent') == "CONFIRM_YES":
                    logger.info("User confirmed using saved route.")
                    return known_route
        
        # --- *** MODIFIED *** ---
        # If no known_route or user said "no", parse the new plan
        logger.info("Parsing new address from AI-generated route_plan.")
        
        # Get the JSON plan from the job
        route_plan_json = job.get('route_plan')
        
        if not route_plan_json:
            logger.error(f"Job {job['id']} has no route_plan JSON. Cannot create route.")
            return None
            
        # Parse the JSON plan into an SDK-executable RoutePlan
        return self.planner.parse_plan_to_route(route_plan_json)

    async def execute_delivery_flow(self, job: Dict[str, Any], route_plan: RoutePlan) -> bool:
        """
        Handles the full SENDING -> RECEIVING -> Security check logic.
        (This function is unchanged, as it already receives the correct RoutePlan)
        """
        self.recorder.save_route_for_return(route_plan)

        move_success = await self._safe_execute_route(route_plan)
        if not move_success:
            await self.state_manager.safe_say(prompts.ERROR_OBSTACLE_BLOCKING)
            return False 

        set_state(mode=AppMode.RECEIVING)
        self.memory.load_conversation_log(job['id'])
        
        await self.state_manager.safe_say(
            f"{prompts.RECEIVER_KNOCK} {prompts.RECEIVER_CONFIRM_IDENTITY.format(job['recipient_name'])}"
        )
        
        text = await self.state_manager.safe_listen()
        self.memory.log_exchange("user", text)
        
        if not text: 
            await self.state_manager.safe_say(prompts.ERROR_NO_ANSWER)
            self.memory.finalize_conversation_log(job['id'])
            return False
            
        ai_data = await self.state_manager.safe_analyze_ai(text)
        if not ai_data or ai_data.get('intent') != 'CONFIRM_YES':
            await self.state_manager.safe_say("My mistake. I will return this message.")
            self.memory.finalize_conversation_log(job['id'])
            return False

        await self.state_manager.safe_say(prompts.RECEIVER_MESSAGE_ANNOUNCE.format(job['sender_name']))

        if job['password']:
            await self.state_manager.safe_say(prompts.RECEIVER_ASK_FOR_PASSWORD)
            text = await self.state_manager.safe_listen()
            self.memory.log_exchange("user", text)
            
            if not text: 
                await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                self.memory.finalize_conversation_log(job['id'])
                return False
                
            ai_data = await self.state_manager.safe_analyze_ai(text)
            spoken_pass = ai_data.get('password')
            
            if not self.security.verify_password(spoken_pass, job['password']):
                await self.state_manager.safe_say(prompts.ERROR_PASSWORD_FAIL)
                await self.state_manager.safe_say(prompts.RECEIVER_ASK_FOR_PASSPORT)
                if not await self.security.verify_identity(job['recipient_name']):
                    await self.state_manager.safe_say(prompts.ERROR_IDENTITY_FAIL)
                    self.memory.finalize_conversation_log(job['id'])
                    return False
        
        await self.state_manager.safe_say(f"The message is: {job['message_body']}")
        
        x, y, heading = self.robot_state.get_state()
        
        self.memory.save_route_for_recipient(
            job['recipient_name'], route_plan, x, y, heading
        )
        
        self.visual_mapper.add_permanent_location(x, y, job['recipient_name'])
        
        await self.state_manager.safe_say(prompts.SAVING_NEW_ADDRESS.format(job['recipient_name']))
        
        self.memory.finalize_conversation_log(job['id'])
        return True

    async def _safe_execute_route(self, route_plan: RoutePlan) -> bool:
        # (Unchanged)
        set_state(isWalking=True)
        try:
            for (direction, steps) in route_plan:
                if direction == MoveRobotDirection.FORWARD:
                    if await self.detector.is_path_blocked():
                        logger.warning("Obstacle detected! Aborting route.")
                        return False 
                
                await self.movement_controller.move(direction, steps)
                await asyncio.sleep(0.5) 
            
            return True 
        except Exception as e:
            logger.error(f"Error during route execution: {e}")
            return False
        finally:
            set_state(isWalking=False)

    async def go_home(self):
        # (Unchanged)
        return_route = self.recorder.get_return_route()
        if return_route:
            await self.state_manager.safe_say(prompts.HEADING_BACK_TO_START)
            set_state(isWalking=True)
            try:
                for (direction, steps) in return_route:
                    await self.movement_controller.move(direction, steps)
                    await asyncio.sleep(0.5)
            finally:
                set_state(isWalking=False)
        else:
            logger.warning("Could not get a return route. Staying in place.")