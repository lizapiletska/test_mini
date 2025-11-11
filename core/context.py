# File: core/context.py

import contextvars
from typing import Any, Dict
from core.app_modes import AppMode

"""
This module implements the "React Context" analog for the robot's state.

It uses `contextvars` to create task-local state variables. This means that
even in a highly concurrent asyncio application, each task (like a
simultaneous listener and a movement command) can have its own
understanding of the state, preventing race conditions.

- set_state() is our "Provider" (or state dispatcher).
- get_state() is our "Consumer" (or state selector).
"""

# Define the context variables with their default values
# These are the global, shared states you specified.
_mode = contextvars.ContextVar("mode", default=AppMode.OFF)
_isSpeaking = contextvars.ContextVar("isSpeaking", default=False)
_isListening = contextvars.ContextVar("isListening", default=False)
_isAiAnalyzing = contextvars.ContextVar("isAiAnalyzing", default=False)
_isWalking = contextvars.ContextVar("isWalking", default=False)

# A map to easily access the context variables by name
STATE_VARS = {
    "mode": _mode,
    "isSpeaking": _isSpeaking,
    "isListening": _isListening,
    "isAiAnalyzing": _isAiAnalyzing,
    "isWalking": _isWalking,
}

def set_state(**kwargs: Any) -> None:
    """
    Sets one or more state variables in the current context.
    
    Example:
        set_state(mode=AppMode.WORKING, isListening=True)
    """
    for key, value in kwargs.items():
        if key in STATE_VARS:
            STATE_VARS[key].set(value)
        else:
            # This is a developer error, so we should raise it
            raise AttributeError(f"'{key}' is not a valid state variable.")

def get_state() -> Dict[str, Any]:
    """
    Retrieves all current state variables from the context as a dictionary.
    """
    return {
        key: var.get()
        for key, var in STATE_VARS.items()
    }

# --- 'get_context_var' method has been removed ---
# It was not used by any part of the application.