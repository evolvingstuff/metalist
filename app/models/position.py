"""
Position management system using fractional indexing for note ordering.

This module implements a string-based position system that allows for:
1. Generating positions between any two existing positions
2. Maintaining a total ordering of notes
3. Efficient string comparison for ordering
"""
from typing import Optional


class Position:
    # Using a-z for better readability in position strings
    ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
    BASE = len(ALPHABET)
    
    @classmethod
    def get_first_position(cls) -> str:
        """Returns the first possible position."""
        return "a1"
    
    @classmethod
    def get_position_between(cls, pos1: Optional[str], pos2: Optional[str]) -> str:
        """
        Generate a position string that sorts between pos1 and pos2.
        
        Args:
            pos1: The lower bound position (or None if getting position before all)
            pos2: The upper bound position (or None if getting position after all)
            
        Returns:
            A new position string that sorts between pos1 and pos2
        """
        # Handle edge cases
        if pos1 is None and pos2 is None:
            return cls.get_first_position()
        if pos1 is None:
            # Generate position before pos2
            return cls._generate_before(pos2)
        if pos2 is None:
            # Generate position after pos1
            return cls._generate_after(pos1)
            
        # If positions are equal, append to first position
        if pos1 == pos2:
            return pos1 + "1"

        # Find the first differing character position
        min_len = min(len(pos1), len(pos2))
        for i in range(min_len):
            if pos1[i] != pos2[i]:
                prefix = pos1[:i]
                c1, c2 = pos1[i], pos2[i]
                mid_char = cls._midpoint_char(c1, c2)
                if mid_char == c1:  # If no midpoint found
                    return pos1 + "1"
                return prefix + mid_char
                
        # If we get here, one string is a prefix of the other
        shorter = pos1 if len(pos1) < len(pos2) else pos2
        longer = pos2 if len(pos1) < len(pos2) else pos1
        next_char = longer[len(shorter)]
        
        # If shorter is pos1, we want to insert between shorter and longer
        # If shorter is pos2, we want to insert between longer and shorter
        if shorter == pos1:
            # Find midpoint between '0' and next_char
            mid_char = cls._midpoint_char('0', next_char)
            return shorter + mid_char
        else:
            # Find midpoint between next_char and 'z'
            mid_char = cls._midpoint_char(next_char, 'z')
            return shorter + mid_char

    @classmethod
    def _generate_before(cls, pos: str) -> str:
        """Generate a position that sorts before the given position."""
        if pos[0] == cls.ALPHABET[0]:
            # If it starts with first character, prepend a new first character
            return cls.ALPHABET[0] + "0"
        # Otherwise, take previous character
        prev_char = cls.ALPHABET[cls.ALPHABET.index(pos[0]) - 1]
        return prev_char + "z"

    @classmethod
    def _generate_after(cls, pos: str) -> str:
        """Generate a position that sorts after the given position."""
        if pos[0] == cls.ALPHABET[-1]:
            # If it starts with last character, append a character
            return pos + "z"
        # Otherwise, take next character
        next_char = cls.ALPHABET[cls.ALPHABET.index(pos[0]) + 1]
        return next_char + "0"

    @classmethod
    def _midpoint_char(cls, c1: str, c2: str) -> str:
        """
        Find a character that sorts between c1 and c2.
        Returns c1 if no midpoint is possible.
        """
        idx1 = cls.ALPHABET.index(c1)
        idx2 = cls.ALPHABET.index(c2)
        
        if idx2 - idx1 > 1:
            # If there's room between characters, pick the midpoint
            mid_idx = (idx1 + idx2) // 2
            return cls.ALPHABET[mid_idx]
        return c1  # Return first char if no midpoint possible

    @staticmethod
    def compare(pos1: str, pos2: str) -> int:
        """
        Compare two position strings.
        Returns:
            -1 if pos1 < pos2
             0 if pos1 == pos2
             1 if pos1 > pos2
        """
        return -1 if pos1 < pos2 else (1 if pos1 > pos2 else 0)
