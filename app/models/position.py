"""Position management using fractional indexing.

This module uses the fractional-indexing library to generate lexicographically ordered
position strings that can always fit a new position between any two existing positions.

The system works by:
1. Using "a0" as the first/starting position
2. For positions after "a0": uses "a1", "a2", etc.
3. For positions before "a0": uses uppercase letters which sort before lowercase in ASCII
   - First position before "a0" is "Zz"
   - Then "Zy", "Zx", etc.
   - Can extend to "YzN", "Yks" etc. when more granularity is needed
   - Maintains short strings (max 3 chars even after 1000 insertions)

This allows for infinite positions in both directions while keeping the strings
as short as possible. The library handles all the complexity of generating these
position strings in a deterministic way."""

from typing import Optional
from fractional_indexing import generate_key_between

class Position:
    @classmethod
    def get_first_position(cls) -> str:
        """Returns the first possible position."""
        return generate_key_between(None, None)
    
    @classmethod
    def get_position_between(cls, pos1: Optional[str], pos2: Optional[str]) -> str:
        """Generate a position string that sorts between pos1 and pos2."""
        return generate_key_between(pos1, pos2)

    @staticmethod
    def compare(pos1: str, pos2: str) -> int:
        """Compare two position strings."""
        if pos1 < pos2:
            return -1
        if pos1 > pos2:
            return 1
        return 0