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
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class PostmanApp:
    """
    The main application class that orchestrates all robot subsystems.
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
        
        # --- *** MODIFIED *** ---
        # Pass the memory manager to the state manager
        self.state_manager = StateManager(self.controller, self.ai, self.memory)
        
        self.conversation = ConversationFlow(self.state_manager)
        
        self.delivery_queue = asyncio.Queue()

    async def boot_sequence(self):
        """
        Runs the initial "Booting" state logic.
        (Function unchanged)
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
                        
                        # --- *** NEW *** ---
                        # Start a new log and add the user's first command
                        self.memory.start_conversation_log()
                        self.memory.log_exchange("user", text)
                        
                        self.conversation.start_new_message_flow(ai_data)
                    
                    elif intent == "FRIENDLY_CHAT":
                        response = ai_data.get("response_text")
                        if response:
                            await self.state_manager.safe_say(response)
                        else:
                            await self.state_manager.safe_say("That's nice to hear. How can I help you?")
                    
                    elif intent == "CONFIRM_NO":
                        await self.state_manager.safe_say("Okay, I'll be here if you need me.")
                    
                    elif intent == "UNKNOWN":
                        await self.state_manager.safe_say("I'm sorry, I didn't understand that command.")

                # 5. Check if a conversation is active
                elif current_state["mode"] == AppMode.COMPOSING and self.conversation.is_in_conversation():
                    
                    text = await self.state_manager.safe_listen()
                    if not text:
                        state = get_state()
                        if not state["isSpeaking"] and not state["isWalking"]:
                            await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                        continue

                    # --- *** NEW *** ---
                    # Log the user's response in the conversation
                    self.memory.log_exchange("user", text)

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
                    # Robot is busy
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in work_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)
                await asyncio.sleep(5) 

    async def delivery_loop(self):
        """
        The main "Postman" loop.
        (Function unchanged)
        """
        while True:
            try:
                job = await self.delivery_queue.get()
                
                logger.info(f"--- 📬 STARTING DELIVERY for job {job['id']} ---")
                
                set_state(mode=AppMode.SENDING)
                await self.state_manager.safe_say(prompts.PROMPT_SENDING_MESSAGES)
                
                route_plan = await self.get_route_for_job(job)
                
                if not route_plan:
                    await self.state_manager.safe_say(f"I'm sorry, I could not understand the address for {job['recipient_name']}.")
                    set_state(mode=AppMode.WORKING)
                    self.delivery_queue.task_done()
                    continue

                delivery_success = await self.execute_delivery_flow(job, route_plan)
                
                if delivery_success:
                    logger.info("Delivery successful. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    await self.go_home()
                else:
                    logger.warning("Delivery failed. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    await self.go_home()
                
                logger.info(f"--- 📬 DELIVERY COMPLETE for job {job['id']} ---")
                set_state(mode=AppMode.WORKING)
                await self.state_manager.safe_say(prompts.PROMPT_ANY_OTHER_MESSAGES)
                
                self.delivery_queue.task_done()

            except Exception as e:
                logger.error(f"Error in delivery_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)

    async def get_route_for_job(self, job: Dict[str, Any]) -> Optional[RoutePlan]:
        """
        (Function unchanged, but now logs user's "yes" or "no")
        """
        recipient_name = job['recipient_name']
        known_route = self.memory.get_known_route_for_recipient(recipient_name)
        
        if known_route:
            await self.state_manager.safe_say(prompts.RETURN_TO_SENDER_CONFIRM_ADDRESS.format(recipient_name))
            text = await self.state_manager.safe_listen()
            
            # --- *** NEW *** ---
            # Log this "meta" confirmation as well
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
        Now logs the delivery conversation.
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
        
        # --- *** NEW *** ---
        # Load the composing log from disk to append to it
        self.memory.load_conversation_log(job['id'])
        
        # 4. Combine "knock" and "identity check"
        await self.state_manager.safe_say(
            f"{prompts.RECEIVER_KNOCK} {prompts.RECEIVER_CONFIRM_IDENTITY.format(job['recipient_name'])}"
        )
        
        # 5. Wait for identity confirmation
        text = await self.state_manager.safe_listen()
        
        # --- *** NEW *** ---
        # Log recipient's response
        self.memory.log_exchange("user", text)
        
        if not text: 
            await self.state_manager.safe_say(prompts.ERROR_NO_ANSWER)
            self.memory.finalize_conversation_log(job['id']) # Save what we have
            return False
            
        ai_data = await self.state_manager.safe_analyze_ai(text)
        if not ai_data or ai_data.get('intent') != 'CONFIRM_YES':
            await self.state_manager.safe_say("My mistake. I will return this message.")
            self.memory.finalize_conversation_log(job['id']) # Save what we have
            return False

        # 5.5. Announce who the message is from
        await self.state_manager.safe_say(prompts.RECEIVER_MESSAGE_ANNOUNCE.format(job['sender_name']))

        # 6. Check protection
        if job['password']:
            await self.state_manager.safe_say(prompts.RECEIVER_ASK_FOR_PASSWORD)
            text = await self.state_manager.safe_listen()
            
            # --- *** NEW *** ---
            # Log recipient's password attempt
            self.memory.log_exchange("user", text)
            
            if not text: 
                await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                self.memory.finalize_conversation_log(job['id']) # Save what we have
                return False
                
            ai_data = await self.state_manager.safe_analyze_ai(text)
            spoken_pass = ai_data.get('password')
            
            if not self.security.verify_password(spoken_pass, job['password']):
                await self.state_manager.safe_say(prompts.ERROR_PASSWORD_FAIL)
                await self.state_manager.safe_say(prompts.RECEIVER_ASK_FOR_PASSPORT)
                if not await self.security.verify_identity(job['recipient_name']):
                    await self.state_manager.safe_say(prompts.ERROR_IDENTITY_FAIL)
                    self.memory.finalize_conversation_log(job['id']) # Save what we have
                    return False
        
        # 7. All checks passed. Deliver message.
        await self.state_manager.safe_say(f"The message is: {job['message_body']}")
        
        # 8. Save this successful route to memory
        self.memory.save_route_for_recipient(job['recipient_name'], route_plan)
        await self.state_manager.safe_say(prompts.SAVING_NEW_ADDRESS.format(job['recipient_name']))
        
        # --- *** NEW *** ---
        # Finalize the *complete* log (composing + delivery)
        self.memory.finalize_conversation_log(job['id'])
        
        return True

    async def safe_execute_route(self, route_plan: RoutePlan) -> bool:
        """
        (Function unchanged)
        """
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
        """
        (Function unchanged)
        """
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
        """
        (Function unchanged)
        """
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