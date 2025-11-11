# === 1. Booting State ===
BOOT_GREETING: str = "Hello. I am starting up."
BOOT_START_SCAN: str = "Analyzing room. Please stand clear."
BOOT_SCAN_COMPLETE: str = "Room analysis complete. Map saved."
BOOT_SYSTEM_READY: str = "I am now in working mode and ready for commands."

# === 2. Working State (Listening & Composing) ===
PROMPT_FOR_COMMAND: str = "How can I help you?"
PROMPT_FOR_MESSAGE: str = "Please say your message clearly."
PROMPT_CONFIRM_CONTINUE: str = "Is this all, or would you like to continue?"
PROMPT_FOR_SENDER_NAME: str = "Got it. Please tell me your name."
PROMPT_FOR_RECIPIENT_NAME: str = "And who is this message for?"
PROMPT_ASK_FOR_PROTECTION: str = "Do you want to protect this message with a password?"
PROMPT_FOR_PASSWORD: str = "Please say the password word."
PROMPT_FOR_ADDRESS: str = "Please give me the address, for example: 50 steps forward, turn 90 left."
PROMPT_MESSAGE_ID_CONFIRM: str = "Your message is saved. The message ID is {}."
PROMPT_ANY_OTHER_MESSAGES: str = "Does anyone else have a message to send?"
PROMPT_SENDING_MESSAGES: str = "Okay, I will begin delivery."

# === 3. Receiving State ===
RECEIVER_KNOCK: str = "Knock knock. I have a delivery."
RECEIVER_CONFIRM_IDENTITY: str = "Hello, are you {}?"
RECEIVER_MESSAGE_ANNOUNCE: str = "You have a message from {}."
RECEIVER_ASK_TO_RECEIVE: str = "Would you like to receive it now?"
RECEIVER_ASK_FOR_PASSWORD: str = "This message is protected. Please say the password."
RECEIVER_ASK_FOR_PASSPORT: str = "I need to verify your identity. Please hold your ID card or passport in front of my camera."

# === 4. After Received / Navigation ===
RETURN_TO_SENDER_CONFIRM_ADDRESS: str = "I have a saved address for {}. Should I deliver there?"
SAVING_NEW_ADDRESS: str = "I have saved this new location for {}."
HEADING_BACK_TO_START: str = "Delivery complete. Returning to my starting point."

# === 5. Error & Fallback Prompts ===
ERROR_NO_ANSWER: str = "It seems no one is here. I will come back later."
ERROR_PASSWORD_FAIL: str = "That is not the correct password."
ERROR_IDENTITY_FAIL: str = "I'm sorry, I cannot verify your identity. I cannot deliver this message."
ERROR_CANNOT_FIND_PERSON: str = "I am having trouble finding {}. I will try again."
ERROR_OBSTACLE_BLOCKING: str = "An obstacle is blocking my path. I will try to find a different way."
ERROR_GENERIC: str = "I'm sorry, an error occurred."
ERROR_LISTEN_TIMEOUT: str = "I didn't hear anything. Let's try again."