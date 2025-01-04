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