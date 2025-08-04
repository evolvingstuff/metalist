"""Text processing utilities for the application"""

import re
from html.parser import HTMLParser


class HTMLStripper(HTMLParser):
    """Custom HTML parser to strip tags and extract plain text"""
    
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    
    def handle_data(self, data):
        self.text.append(data)
    
    def get_data(self):
        return ''.join(self.text)


def strip_html(html_content: str) -> str:
    """
    Strip HTML tags from content and return plain text.
    
    Args:
        html_content: HTML string to strip
        
    Returns:
        Plain text with HTML tags removed
    """
    if not html_content:
        return ""
    
    # Use our custom parser to strip HTML
    stripper = HTMLStripper()
    stripper.feed(html_content)
    text = stripper.get_data()
    
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()