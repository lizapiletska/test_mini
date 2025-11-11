# File: core/delivery_flow.py

import logging
from typing import Dict, Any, Optional

from ai.memory import MemoryManager
from ai.security import SecurityManager
from config import prompts
from core.app_modes import AppMode
from core.context import set_state
from core.state_manager import StateManager
from robot.movement.route_recorder import RouteRecorder
from robot.navigation.planner import Planner, RoutePlan
from robot.navigation.obstacle_detector import ObstacleDetector

logger = logging.getLogger(__name__)

# This class will hold all the modules needed for delivery
class DeliveryFlow:
    def __init__(self,
                 state_manager: StateManager,
                 memory: MemoryManager,
                 planner: Planner,
                 security: SecurityManager,
                 recorder: RouteRecorder,
                 detector: ObstacleDetector):
        
        self.state_manager = state_manager
        self.memory = memory
        self.planner = planner
        self.security = security
        self.recorder = recorder
        self.detector = detector

    async def get_route_for_job(self, job: Dict[str, Any]) -> Optional[RoutePlan]:
        """
        Gets a route for a job, either from memory or by
        parsing the address text.
        """
        recipient_name = job['recipient_name']
        known_route = self.memory.get_known_route_for_recipient(recipient_name)
        
        if known_route:
            await self.state_manager.safe_say(prompts.RETURN_TO_SENDER_CONFIRM_ADDRESS.format(recipient_name))
            text = await self.state_manager.safe_listen()
            
            # Log this "meta" confirmation
            self.memory.log_exchange("user", text) 
            
            if text:
                ai_data = await self.state_manager.safe_analyze_ai(text)
                if ai_data and ai_data.get('intent') == "CONFIRM_YES":
                    logger.info("User confirmed using saved route.")
                    return known_route
        
        logger.info("Parsing new address text.")
        address_text = job.get('address_text')
        if not address_text:
            return None
        return self.planner.parse_address_to_route(address_text)

    async def execute_delivery_flow(self, job: Dict[str, Any], route_plan: RoutePlan) -> bool:
        """
        Handles the full SENDING -> RECEIVING -> Security check logic.
        Logs the delivery conversation.
        """
        # 1. Save route for return trip
        self.recorder.save_route_for_return(route_plan)

        # 2. Execute the route safely
        move_success = await self._safe_execute_route(route_plan)
        if not move_success:
            await self.state_manager.safe_say(prompts.ERROR_OBSTACLE_BLOCKING)
            return False 

        # 3. Arrived at destination, switch to RECEIVING mode
        set_state(mode=AppMode.RECEIVING)
        
        # Load the composing log from disk to append to it
        self.memory.load_conversation_log(job['id'])
        
        # 4. Combine "knock" and "identity check"
        await self.state_manager.safe_say(
            f"{prompts.RECEIVER_KNOCK} {prompts.RECEIVER_CONFIRM_IDENTITY.format(job['recipient_name'])}"
        )
        
        # 5. Wait for identity confirmation
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

        # 5.5. Announce who the message is from
        await self.state_manager.safe_say(prompts.RECEIVER_MESSAGE_ANNOUNCE.format(job['sender_name']))

        # 6. Check protection
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
        
        # 7. All checks passed. Deliver message.
        await self.state_manager.safe_say(f"The message is: {job['message_body']}")
        
        # 8. Save this successful route to memory
        self.memory.save_route_for_recipient(job['recipient_name'], route_plan)
        await self.state_manager.safe_say(prompts.SAVING_NEW_ADDRESS.format(job['recipient_name']))
        
        # Finalize the *complete* log (composing + delivery)
        self.memory.finalize_conversation_log(job['id'])
        
        return True

    async def _safe_execute_route(self, route_plan: RoutePlan) -> bool:
        """
        Executes a route plan, checking for obstacles.
        (This was a method in PostmanApp, now it's here)
        """
        set_state(isWalking=True)
        try:
            for (direction, steps) in route_plan:
                if direction == MoveRobotDirection.FORWARD:
                    if await self.detector.is_path_blocked():
                        logger.warning("Obstacle detected! Aborting route.")
                        return False 
                
                await self.state_manager.robot.move(direction, steps) # Call controller directly
                await asyncio.sleep(0.5) 
            
            return True 
        except Exception as e:
            logger.error(f"Error during route execution: {e}")
            return False
        finally:
            set_state(isWalking=False)

    async def go_home(self):
        """
        Calculates and executes the return-to-start route.
        (This was a method in PostmanApp, now it's here)
        """
        return_route = self.recorder.get_return_route()
        if return_route:
            await self.state_manager.safe_say(prompts.HEADING_BACK_TO_START)
            set_state(isWalking=True)
            try:
                for (direction, steps) in return_route:
                    await self.state_manager.robot.move(direction, steps) # Call controller directly
                    await asyncio.sleep(0.5)
            finally:
                set_state(isWalking=False)
        else:
            logger.warning("Could not get a return route. Staying in place.")