"""Text processing utilities for the application."""

import re
from html.parser import HTMLParser


_IGNORE_TAGS = {"script", "style", "noscript"}

_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "dl",
    "dt",
    "dd",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}


class HTMLStripper(HTMLParser):
    """Custom HTML parser to strip tags and extract plain text"""
    
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in _IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if normalized in _BLOCK_TAGS:
            self.text.append(" ")

    def handle_startendtag(self, tag: str, attrs) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in _BLOCK_TAGS:
            self.text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _IGNORE_TAGS:
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return
        if normalized in _BLOCK_TAGS:
            self.text.append(" ")
    
    def handle_data(self, data):
        if self._ignore_depth > 0:
            return
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
    if not isinstance(html_content, str):
        raise TypeError(f"html_content must be a string, got {type(html_content)}")
    if html_content == "":
        return ""
    
    # Use our custom parser to strip HTML
    stripper = HTMLStripper()
    stripper.feed(html_content)
    text = stripper.get_data()
    
    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
