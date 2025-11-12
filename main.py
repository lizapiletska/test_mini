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

# --- NEW ---
from vision.visual_mapper import VisualMapper
from core.delivery_flow import DeliveryFlow
from core.robot_state import RobotState
from core.movement_controller import MovementController

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
        # --- Initialize all modules (in order) ---
        
        # 1. Low-level Hardware & State
        self.controller = RobotController()
        self.robot_state = RobotState()
        
        # 2. Visualizer (requires state)
        self.visual_mapper = VisualMapper(self.robot_state)
        
        # 3. Guarded Movement (requires controller, state, and visualizer)
        self.movement_controller = MovementController(
            self.controller, self.robot_state, self.visual_mapper
        )
        
        # 4. Navigation & Mapping (requires hardware and movement)
        self.detector = ObstacleDetector(self.controller)
        self.planner = Planner()
        self.mapper = Mapper(
            self.controller, self.visual_mapper, self.robot_state, self.movement_controller
        )
        self.recorder = RouteRecorder()

        # 5. AI & Memory Modules
        self.ai = AIOrchestrator()
        self.security = SecurityManager(self.controller)
        self.memory = MemoryManager()
        
        # 6. Core Logic & Flows (requires all other modules)
        self.state_manager = StateManager(self.controller, self.ai, self.memory)
        self.conversation = ConversationFlow(self.state_manager)
        
        # --- *** MODIFIED *** ---
        # Pass the new modules to DeliveryFlow
        self.delivery_flow = DeliveryFlow(
            self.state_manager,
            self.memory,
            self.planner,
            self.security,
            self.recorder,
            self.detector,
            self.movement_controller,
            self.robot_state,      # <-- NEW
            self.visual_mapper     # <-- NEW
        )
        
        # 7. Job Queue
        self.delivery_queue = asyncio.Queue()

    # --- *** NEW FUNCTION *** ---
    def load_and_plot_saved_locations(self):
        """
        Loads all saved profile locations from disk and
        tells the visualizer to plot them.
        """
        try:
            locations = self.memory.get_all_saved_locations()
            if locations:
                self.visual_mapper.load_permanent_locations(locations)
        except Exception as e:
            logger.error(f"Failed to load and plot saved locations: {e}")

    async def boot_sequence(self):
        """
        Runs the initial "Booting" state logic.
        """
        logger.info("--- 🤖 ROBOT BOOTING ---")
        set_state(mode=AppMode.BOOTING)
        
        await self.state_manager.safe_say(prompts.BOOT_GREETING)
        
        # Start the visualizer window.
        self.visual_mapper.start()
        
        # --- *** MODIFIED *** ---
        # Load saved profiles *before* scanning
        self.load_and_plot_saved_locations()
        
        if not self.mapper.load_map_from_file():
            logger.info("No map file found. Starting new room scan.")
            await self.state_manager.safe_say(prompts.BOOT_START_SCAN)
            await self.mapper.scan_and_build_map() 
        else:
            logger.info("Successfully loaded existing map file.")
            map_data = self.mapper.get_map_data()
            if map_data:
                self.visual_mapper.load_obstacles(map_data)
        
        await self.state_manager.safe_say(prompts.BOOT_SYSTEM_READY)
        set_state(mode=AppMode.WORKING)
        logger.info("--- 🤖 BOOTING COMPLETE ---")

    async def work_loop(self):
        """
        The main "Working" loop.
        (Unchanged)
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
        (Unchanged)
        """
        while True:
            try:
                job = await self.delivery_queue.get()
                
                logger.info(f"--- 📬 STARTING DELIVERY for job {job['id']} ---")
                
                set_state(mode=AppMode.SENDING)
                await self.state_manager.safe_say(prompts.PROMPT_SENDING_MESSAGES)
                
                route_plan = await self.delivery_flow.get_route_for_job(job)
                
                if not route_plan:
                    await self.state_manager.safe_say(f"I'm sorry, I could not understand the address for {job['recipient_name']}.")
                    set_state(mode=AppMode.WORKING)
                    self.delivery_queue.task_done()
                    continue

                delivery_success = await self.delivery_flow.execute_delivery_flow(job, route_plan)
                
                if delivery_success:
                    logger.info("Delivery successful. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    await self.delivery_flow.go_home()
                else:
                    logger.warning("Delivery failed. Returning to start.")
                    set_state(mode=AppMode.RETURNING)
                    await self.delivery_flow.go_home()
                
                logger.info(f"--- 📬 DELIVERY COMPLETE for job {job['id']} ---")
                set_state(mode=AppMode.WORKING)
                await self.state_manager.safe_say(prompts.PROMPT_ANY_OTHER_MESSAGES)
                
                self.delivery_queue.task_done()

            except Exception as e:
                logger.error(f"Error in delivery_loop: {e}", exc_info=True)
                await self.state_manager.safe_say(prompts.ERROR_GENERIC)

    async def run(self):
        """
        Main entry point for the application.
        (Unchanged)
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
            if self.visual_mapper:
                self.visual_mapper.stop()
            
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