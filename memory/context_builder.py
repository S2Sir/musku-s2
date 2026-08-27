"""context_builder.py - 3-Layer Memory Architecture.

Prepares the memory context for Gemini Live.
L0: Always Available (Name, Identity, Core preferences)
L1: Current Session (Recent conversation, Active tasks)
L2: On Demand (Old conversations)
"""

import logging
# from .store import mstore
# from .chat import mchat

logger = logging.getLogger("MUSKU.ContextBuilder")

class ContextBuilder:
    def build_system_prompt(self, base_prompt: str) -> str:
        """Injects L0 and L1 memory into the system prompt."""
        logger.info("Building system prompt with L0/L1 memory")
        
        # L0 Memory
        l0_memory = "Boss Name: S2Sir\nCore Preferences: Fast responses, professional"
        
        # L1 Memory
        l1_memory = "Active Tasks: Finish architecture migration"
        
        return f"{base_prompt}\n\n--- CORE MEMORY (L0) ---\n{l0_memory}\n\n--- CURRENT CONTEXT (L1) ---\n{l1_memory}"

context_builder = ContextBuilder()
