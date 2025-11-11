# File: main.py

import asyncio
import logging
import sys
from typing import Optional, Dict, Any, List

# --- Core App Logic ---
from core.app_modes import AppMode
from core.context import set_state, get_state
from core.state_manager import StateManager
from config import settings, prompts

# --- Robot Modules ---
from robot.controller import RobotController
from robot.navigation.mapper import Mapper
from robot.navigation.planner import Planner, RoutePlan
from robot.navigation.obstacle_detector import ObstacleDetector
from robot.movement.route_recorder import RouteRecorder
from mini.apis.api_action import MoveRobotDirection

# --- AI Modules ---
from ai.orchestrator import AIOrchestrator
from ai.conversation_flow import ConversationFlow, ConversationStep
from ai.security import SecurityManager
from ai.memory import MemoryManager

# --- Setup Logging ---
# Configure logging to show info-level messages
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class PostmanApp:
    """
    The main application class that orchestrates all robot subsystems.
    It holds instances of all managers and runs the main event loops.
    """
    def __init__(self):
        # Initialize all modules
        self.controller = RobotController()
        self.detector = ObstacleDetector(self.controller)
        self.planner = Planner()
        self.mapper = Mapper(self.controller)
        self.ai = AIOrchestrator()
        self.security = SecurityManager(self.controller)
        self.memory = MemoryManager()
        self.recorder = RouteRecorder()
        
        self.state_manager = StateManager(self.controller, self.ai)
        self.conversation = ConversationFlow(self.state_manager)
        
        # A queue to hold message jobs that are ready for delivery
        self.delivery_queue = asyncio.Queue()

    async def boot_sequence(self):
        """
        Runs the initial "Booting" state logic.
        """
        logger.info("--- 🤖 ROBOT BOOTING ---")
        set_state(mode=AppMode.BOOTING)
        
        await self.state_manager.safe_say(prompts.BOOT_GREETING)
        
        if not self.mapper.load_map_from_file():
            logger.info("No map file found. Starting new room scan.")
            await self.state_manager.safe_say(prompts.BOOT_START_SCAN)
            await self.mapper.scan_and_build_map()
        else:
            logger.info("Successfully loaded existing map file.")
            
        await self.state_manager.safe_say(prompts.BOOT_SYSTEM_READY)
        
        set_state(mode=AppMode.WORKING)
        
        logger.info("--- 🤖 BOOTING COMPLETE ---")

    async def work_loop(self):
        """
        The main "Working" loop.
        Listens for commands and handles conversation state.
        """
        while True:
            try:
                # 1. Check if we should be listening
                current_state = get_state()
                if current_state["mode"] == AppMode.WORKING and not self.conversation.is_in_conversation():
                    
                    # 2. Listen for user input
                    text = await self.state_manager.safe_listen()
                    if not text:
                        state = get_state()
                        if not state["isSpeaking"] and not state["isWalking"]:
                            await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                        continue 

                    # 3. Analyze text with AI
                    ai_data = await self.state_manager.safe_analyze_ai(text)
                    if not ai_data or "intent" not in ai_data:
                        continue 

                    intent = ai_data.get("intent")
                    
                    # 4. Decide what to do with the intent
                    if intent == "SEND_MESSAGE":
                        set_state(mode=AppMode.COMPOSING)
                        self.conversation.start_new_message_flow(ai_data)
                    
                    elif intent == "FRIENDLY_CHAT":
                        response = ai_data.get("response_text")
                        if response:
                            await self.state_manager.safe_say(response)
                        else:
                            await self.state_manager.safe_say("That's nice to hear. How can I help you?")
                    
                    elif intent == "CONFIRM_NO":
                        # User said "no" to a question like "any other messages?"
                        await self.state_manager.safe_say("Okay, I'll be here if you need me.")
                    
                    elif intent == "UNKNOWN":
                        # User said something the AI just didn't get
                        await self.state_manager.safe_say("I'm sorry, I didn't understand that command.")

                # 5. Check if a conversation is active
                elif current_state["mode"] == AppMode.COMPOSING and self.conversation.is_in_conversation():
                    
                    text = await self.state_manager.safe_listen()
                    if not text:
                        state = get_state()
                        if not state["isSpeaking"] and not state["isWalking"]:
                            await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                        continue

                    ai_data = await self.state_manager.safe_analyze_ai(text)
                    if not ai_data:
                        continue
                        
                    # 6. Pass the response to the conversation flow
                    await self.conversation.handle_ai_response(ai_data)
                    
                    # 7. Check if the conversation finished a job
                    job = self.conversation.get_completed_job()
                    if job:
                        logger.info(f"New message job created: {job['id']}")
                        await self.delivery_queue.put(job)
                
                else:
                    # Robot is busy (mode is SENDING, RECEIVING, etc.)
                    # Wait 1 second before checking again.
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in work_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)
                await asyncio.sleep(5) 

    async def delivery_loop(self):
        """
        The main "Postman" loop.
        Waits for jobs in the queue and processes them one by one.
        """
        while True:
            try:
                # 1. Wait for a job
                job = await self.delivery_queue.get()
                
                # Now that we have a job, we take control.
                logger.info(f"--- 📬 STARTING DELIVERY for job {job['id']} ---")
                
                # 2. Set SENDING state
                set_state(mode=AppMode.SENDING)
                await self.state_manager.safe_say(prompts.PROMPT_SENDING_MESSAGES)
                
                # 3. Get the route
                route_plan = await self.get_route_for_job(job)
                
                if not route_plan:
                    await self.state_manager.safe_say(f"I'm sorry, I could not understand the address for {job['recipient_name']}.")
                    set_state(mode=AppMode.WORKING) # Go back to working
                    self.delivery_queue.task_done()
                    continue

                # 4. Execute the delivery
                delivery_success = await self.execute_delivery_flow(job, route_plan)
                
                # 5. Go home
                if delivery_success:
                    logger.info("Delivery successful. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    await self.go_home()
                else:
                    logger.warning("Delivery failed. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    await self.go_home() # Go home even if it fails
                
                # 6. Delivery is 100% complete. Now ask for more messages.
                logger.info(f"--- 📬 DELIVERY COMPLETE for job {job['id']} ---")
                set_state(mode=AppMode.WORKING) # Set mode back to WORKING
                await self.state_manager.safe_say(prompts.PROMPT_ANY_OTHER_MESSAGES)
                
                self.delivery_queue.task_done()

            except Exception as e:
                logger.error(f"Error in delivery_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)

    async def get_route_for_job(self, job: Dict[str, Any]) -> Optional[RoutePlan]:
        recipient_name = job['recipient_name']
        known_route = self.memory.get_known_route_for_recipient(recipient_name)
        
        if known_route:
            await self.state_manager.safe_say(prompts.RETURN_TO_SENDER_CONFIRM_ADDRESS.format(recipient_name))
            text = await self.state_manager.safe_listen()
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
        (MODIFIED for a more natural interaction flow)
        """
        # 1. Save route for return trip
        self.recorder.save_route_for_return(route_plan)

        # 2. Execute the route safely
        move_success = await self.safe_execute_route(route_plan)
        if not move_success:
            await self.state_manager.safe_say(prompts.ERROR_OBSTACLE_BLOCKING)
            return False 

        # 3. Arrived at destination, switch to RECEIVING mode
        set_state(mode=AppMode.RECEIVING)
        
        # 4. --- *** THIS IS THE FIX *** ---
        # Combine "knock" and "identity check" and ask immediately.
        await self.state_manager.safe_say(
            f"{prompts.RECEIVER_KNOCK} {prompts.RECEIVER_CONFIRM_IDENTITY.format(job['recipient_name'])}"
        )
        
        # 5. Wait for identity confirmation
        text = await self.state_manager.safe_listen()
        if not text: 
            # If they don't answer, use the ERROR_NO_ANSWER prompt
            await self.state_manager.safe_say(prompts.ERROR_NO_ANSWER)
            return False
            
        ai_data = await self.state_manager.safe_analyze_ai(text)
        if not ai_data or ai_data.get('intent') != 'CONFIRM_YES':
            # User said "no, I'm not Oksana"
            await self.state_manager.safe_say("My mistake. I will return this message.")
            return False

        # --- *** THIS IS THE SECOND FIX *** ---
        # 5.5. Announce who the message is from
        await self.state_manager.safe_say(prompts.RECEIVER_MESSAGE_ANNOUNCE.format(job['sender_name']))
        # --- *** END OF FIXES *** ---

        # 6. Check protection
        if job['password']:
            await self.state_manager.safe_say(prompts.RECEIVER_ASK_FOR_PASSWORD)
            text = await self.state_manager.safe_listen()
            if not text: 
                await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                return False
                
            ai_data = await self.state_manager.safe_analyze_ai(text)
            spoken_pass = ai_data.get('password')
            
            if not self.security.verify_password(spoken_pass, job['password']):
                await self.state_manager.safe_say(prompts.ERROR_PASSWORD_FAIL)
                await self.state_manager.safe_say(prompts.RECEIVER_ASK_FOR_PASSPORT)
                if not await self.security.verify_identity(job['recipient_name']):
                    await self.state_manager.safe_say(prompts.ERROR_IDENTITY_FAIL)
                    return False
        
        # 7. All checks passed. Deliver message.
        # We already announced the sender, so just give the body.
        await self.state_manager.safe_say(f"The message is: {job['message_body']}")
        
        # 8. Save this successful route to memory
        self.memory.save_route_for_recipient(job['recipient_name'], route_plan)
        await self.state_manager.safe_say(prompts.SAVING_NEW_ADDRESS.format(job['recipient_name']))
        
        return True

    async def safe_execute_route(self, route_plan: RoutePlan) -> bool:
        set_state(isWalking=True)
        try:
            for (direction, steps) in route_plan:
                if direction == MoveRobotDirection.FORWARD:
                    if await self.detector.is_path_blocked():
                        logger.warning("Obstacle detected! Aborting route.")
                        return False 
                
                await self.controller.move(direction, steps)
                await asyncio.sleep(0.5) 
            
            return True 
        except Exception as e:
            logger.error(f"Error during route execution: {e}")
            return False
        finally:
            set_state(isWalking=False)

    async def go_home(self):
        return_route = self.recorder.get_return_route()
        if return_route:
            await self.state_manager.safe_say(prompts.HEADING_BACK_TO_START)
            set_state(isWalking=True)
            try:
                for (direction, steps) in return_route:
                    await self.controller.move(direction, steps)
                    await asyncio.sleep(0.5)
            finally:
                set_state(isWalking=False)
        else:
            logger.warning("Could not get a return route. Staying in place.")

    async def run(self):
        try:
            if not await self.controller.connect():
                logger.critical("Failed to connect to robot. Exiting.")
                return

            await self.boot_sequence()
            
            work_task = asyncio.create_task(self.work_loop())
            delivery_task = asyncio.create_task(self.delivery_loop())
            
            await asyncio.gather(work_task, delivery_task)

        except asyncio.CancelledError:
            logger.info("Application shutting down...")
        finally:
            if self.controller.device:
                await self.controller.disconnect()
            logger.info("Shutdown complete.")


# --- Run the Application ---
if __name__ == "__main__":
    app = PostmanApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C).")