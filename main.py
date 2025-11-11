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

# --- *** NEW *** ---
from vision.visual_mapper import VisualMapper
from core.delivery_flow import DeliveryFlow

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
        
        # --- *** NEW *** ---
        # Initialize the visualizer
        self.visual_mapper = VisualMapper()
        
        # Pass the visualizer to the Mapper
        self.mapper = Mapper(self.controller, self.visual_mapper)
        
        self.ai = AIOrchestrator()
        self.security = SecurityManager(self.controller)
        self.memory = MemoryManager()
        self.recorder = RouteRecorder()
        
        self.state_manager = StateManager(self.controller, self.ai, self.memory)
        self.conversation = ConversationFlow(self.state_manager)
        
        # --- *** NEW *** ---
        # Initialize the new DeliveryFlow class
        self.delivery_flow = DeliveryFlow(
            self.state_manager,
            self.memory,
            self.planner,
            self.security,
            self.recorder,
            self.detector
        )
        
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
            # This will now launch the pop-up window
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
        (Unchanged from your last version)
        """
        while True:
            try:
                current_state = get_state()
                if current_state["mode"] == AppMode.WORKING and not self.conversation.is_in_conversation():
                    
                    text = await self.state_manager.safe_listen()
                    if not text:
                        state = get_state()
                        if not state["isSpeaking"] and not state["isWalking"]:
                            await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                        continue 

                    ai_data = await self.state_manager.safe_analyze_ai(text)
                    if not ai_data or "intent" not in ai_data:
                        continue 

                    intent = ai_data.get("intent")
                    
                    if intent == "SEND_MESSAGE":
                        set_state(mode=AppMode.COMPOSING)
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

                elif current_state["mode"] == AppMode.COMPOSING and self.conversation.is_in_conversation():
                    
                    text = await self.state_manager.safe_listen()
                    if not text:
                        state = get_state()
                        if not state["isSpeaking"] and not state["isWalking"]:
                            await self.state_manager.safe_say(prompts.ERROR_LISTEN_TIMEOUT)
                        continue

                    self.memory.log_exchange("user", text)

                    ai_data = await self.state_manager.safe_analyze_ai(text)
                    if not ai_data:
                        continue
                        
                    await self.conversation.handle_ai_response(ai_data)
                    
                    job = self.conversation.get_completed_job()
                    if job:
                        logger.info(f"New message job created: {job['id']}")
                        await self.delivery_queue.put(job)
                
                else:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in work_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)
                await asyncio.sleep(5) 

    async def delivery_loop(self):
        """
        The main "Postman" loop.
        Now delegates all logic to the DeliveryFlow.
        """
        while True:
            try:
                job = await self.delivery_queue.get()
                
                logger.info(f"--- 📬 STARTING DELIVERY for job {job['id']} ---")
                
                set_state(mode=AppMode.SENDING)
                await self.state_manager.safe_say(prompts.PROMPT_SENDING_MESSAGES)
                
                # --- *** MODIFIED *** ---
                # Call the new delivery_flow class
                route_plan = await self.delivery_flow.get_route_for_job(job)
                
                if not route_plan:
                    await self.state_manager.safe_say(f"I'm sorry, I could not understand the address for {job['recipient_name']}.")
                    set_state(mode=AppMode.WORKING)
                    self.delivery_queue.task_done()
                    continue

                # --- *** MODIFIED *** ---
                # Call the new delivery_flow class
                delivery_success = await self.delivery_flow.execute_delivery_flow(job, route_plan)
                
                if delivery_success:
                    logger.info("Delivery successful. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    # --- *** MODIFIED *** ---
                    await self.delivery_flow.go_home()
                else:
                    logger.warning("Delivery failed. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    # --- *** MODIFIED *** ---
                    await self.delivery_flow.go_home()
                
                logger.info(f"--- 📬 DELIVERY COMPLETE for job {job['id']} ---")
                set_state(mode=AppMode.WORKING)
                await self.state_manager.safe_say(prompts.PROMPT_ANY_OTHER_MESSAGES)
                
                self.delivery_queue.task_done()

            except Exception as e:
                logger.error(f"Error in delivery_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)

    # --- ALL DELIVERY HELPER FUNCTIONS HAVE BEEN MOVED ---
    # get_route_for_job -> self.delivery_flow.get_route_for_job
    # execute_delivery_flow -> self.delivery_flow.execute_delivery_flow
    # safe_execute_route -> self.delivery_flow._safe_execute_route
    # go_home -> self.delivery_flow.go_home

    async def run(self):
        """
        Main entry point for the application.
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