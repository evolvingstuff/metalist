import { CONFIG } from './config.js';

export const CommentUtils = {
    
    findCommentPatterns(htmlContent) {
        if (!htmlContent || !CONFIG.COMMENT_HIGHLIGHTING.ENABLE) {
            return [];
        }
        
        const commentRegex = /\/\*[^*]*\*\//g;
        const matches = [];
        let match;
        
        while ((match = commentRegex.exec(htmlContent)) !== null) {
            matches.push({
                text: match[0],
                start: match.index,
                end: match.index + match[0].length
            });
        }
        
        return matches;
    },
    
    /**
     * Wraps comment patterns with highlighting spans
     * Preserves cursor position during DOM manipulation
     */
    highlightComments(element) {
        if (!element || !CONFIG.COMMENT_HIGHLIGHTING.ENABLE) {
            return;
        }
        
        // Store cursor position relative to text content
        const selection = window.getSelection();
        let cursorOffset = 0;
        
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            if (element.contains(range.startContainer)) {
                // CRITICAL: Check if cursor is in an empty element (e.g., empty div after Enter key)
                // 
                // When contentEditable creates empty block elements (divs), the cursor can be positioned
                // inside them even though they contain no text nodes. Our text-offset-based cursor 
                // preservation logic cannot handle these cases because:
                // 1. TreeWalker with SHOW_TEXT filter cannot find cursors in elements with no text
                // 2. _getTextOffsetInElement would return incorrect fallback values
                // 3. After DOM manipulation, _setTextOffsetInElement would place cursor at wrong position
                //
                // This caused the "cursor jump" bug where pressing Enter would briefly show cursor on 
                // new line, then jump to end of content after highlighting ran.
                //
                // Solution: Skip highlighting entirely when cursor is in empty element because:
                // - There's no text to highlight anyway (empty element = no comment patterns)
                // - Avoiding DOM manipulation preserves cursor position naturally
                // - Highlighting will resume once user types text into the empty element
                const container = range.startContainer;
                const isInEmptyElement = 
                    (container.nodeType === Node.ELEMENT_NODE && !container.textContent) ||
                    (container.nodeType === Node.TEXT_NODE && container.parentNode && !container.parentNode.textContent);
                
                if (isInEmptyElement) {
                    return;
                }
                
                cursorOffset = this._getTextOffsetInElement(element, range.startContainer, range.startOffset);
            }
        }
        
        // First remove any existing highlighting
        this.removeHighlighting(element);
        
        const walker = document.createTreeWalker(
            element,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        const textNodes = [];
        let node;
        while (node = walker.nextNode()) {
            textNodes.push(node);
        }
        
        textNodes.forEach(textNode => {
            const content = textNode.textContent;
            const comments = this.findCommentPatterns(content);
            
            if (comments.length === 0) return;
            
            const parent = textNode.parentNode;
            const fragment = document.createDocumentFragment();
            let lastEnd = 0;
            
            comments.forEach(comment => {
                // Add text before comment
                if (comment.start > lastEnd) {
                    fragment.appendChild(
                        document.createTextNode(content.slice(lastEnd, comment.start))
                    );
                }
                
                // Create highlighted span for comment
                const span = document.createElement('span');
                span.className = CONFIG.COMMENT_HIGHLIGHTING.CSS_CLASS;
                span.textContent = comment.text;
                fragment.appendChild(span);
                
                lastEnd = comment.end;
            });
            
            // Add remaining text after last comment
            if (lastEnd < content.length) {
                fragment.appendChild(
                    document.createTextNode(content.slice(lastEnd))
                );
            }
            
            parent.replaceChild(fragment, textNode);
        });
        
        // Restore cursor position
        this._setTextOffsetInElement(element, cursorOffset);
    },
    
    /**
     * Removes comment highlighting spans, keeping just the text content
     */
    removeHighlighting(element) {
        if (!element) return;
        
        const spans = element.querySelectorAll(`.${CONFIG.COMMENT_HIGHLIGHTING.CSS_CLASS}`);
        spans.forEach(span => {
            span.replaceWith(document.createTextNode(span.textContent));
        });
    },
    
    /**
     * Gets clean HTML content with comment spans stripped
     */
    getCleanContent(element) {
        if (!element) return '';
        
        const clone = element.cloneNode(true);
        this.removeHighlighting(clone);
        return clone.innerHTML;
    },
    
    _getTextOffsetInElement(element, targetNode, targetOffset) {
        const walker = document.createTreeWalker(
            element,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let totalOffset = 0;
        let node;
        
        while (node = walker.nextNode()) {
            if (node === targetNode) {
                return totalOffset + targetOffset;
            }
            totalOffset += node.textContent.length;
        }
        
        return totalOffset;
    },
    
    _setTextOffsetInElement(element, targetOffset) {
        const walker = document.createTreeWalker(
            element,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let currentOffset = 0;
        let node;
        
        while (node = walker.nextNode()) {
            const nodeLength = node.textContent.length;
            if (currentOffset + nodeLength >= targetOffset) {
                const range = document.createRange();
                const offsetInNode = Math.min(targetOffset - currentOffset, nodeLength);
                range.setStart(node, offsetInNode);
                range.collapse(true);
                
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                return;
            }
            currentOffset += nodeLength;
        }
        
        // If we get here, place cursor at end
        const range = document.createRange();
        range.selectNodeContents(element);
        range.collapse(false);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }
};