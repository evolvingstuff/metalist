#!/usr/bin/env python
"""Check for soft error handling patterns that violate CLAUDE.md"""
import os
import re
import sys

# Python patterns that indicate soft error handling
PYTHON_BANNED_PATTERNS = [
    (r'\btry:', 'try/except block'),
    (r'\bexcept\b', 'except clause'),
    (r'Optional\[', 'Optional type'),
    (r'\.get\([^,]+,[^)]+\)', '.get() with default value'),
    (r'if not .+:\s*\n?\s*\w+\s*=', 'fallback assignment'),
]

# JavaScript patterns that indicate soft error handling
JS_BANNED_PATTERNS = [
    (r'\btry\s*{', 'try/catch block'),
    (r'\bcatch\s*\(', 'catch clause'),
    (r'\.catch\(', '.catch() promise handler'),
    (r'\?\?', 'nullish coalescing operator'),
    (r'\?.', 'optional chaining'),
    (r'if\s*\(!.+\)\s*{\s*\n?\s*.+\s*=', 'fallback assignment'),
    (r'[^=]=\s*.+\s*\|\|\s*.+', 'OR operator fallback'),
    (r'console\.warn\(', 'console.warn (should throw instead)'),
    (r'console\.error\(', 'console.error (should throw instead)'),
]

# ALLOWED EXCEPTIONS - Add specific file:line combinations that are approved
# Format: "filepath:line_number" or "filepath:*" to allow all in that file
ALLOWED = [
    # Example: "posts/views.py:45",  # Approved try/catch for specific reason
    # Example: "venv/*:*",  # Ignore all in venv
    # Example: "static/js/vendor/*:*",  # Ignore vendor files
]

def is_allowed(filepath, line_num):
    """Check if this specific error is in the allowlist"""
    # Check for exact match
    if f"{filepath}:{line_num}" in ALLOWED:
        return True
    # Check for wildcard match
    if f"{filepath}:*" in ALLOWED:
        return True
    # Check for directory wildcards
    for allowed in ALLOWED:
        if allowed.endswith("/*:*"):
            dir_pattern = allowed[:-4]  # Remove /*:*
            if filepath.startswith(dir_pattern):
                return True
    return False

found_issues = False

for root, dirs, files in os.walk('.'):
    # Skip venv, git, node_modules directories
    if 'venv' in root or '.git' in root or '__pycache__' in root or 'node_modules' in root:
        continue
        
    for file in files:
        filepath = os.path.join(root, file)
        
        # Check Python files
        if file.endswith('.py'):
            # Skip checking this script itself
            if filepath == './check_errors.py':
                continue
            with open(filepath, 'r') as f:
                content = f.read()
                lines = content.split('\n')
                
            for pattern, description in PYTHON_BANNED_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        if not is_allowed(filepath, i):
                            print(f"{filepath}:{i} - Found {description}: {line.strip()}")
                            found_issues = True
                        else:
                            print(f"{filepath}:{i} - ALLOWED {description}: {line.strip()}")
        
        # Check JavaScript/TypeScript files
        elif file.endswith(('.js', '.jsx', '.ts', '.tsx')):
            # Skip minified files
            if '.min.' in file:
                continue
            # Skip files that can't be read as text
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                
            for pattern, description in JS_BANNED_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        if not is_allowed(filepath, i):
                            print(f"{filepath}:{i} - Found {description}: {line.strip()}")
                            found_issues = True
                        else:
                            print(f"{filepath}:{i} - ALLOWED {description}: {line.strip()}")

if found_issues:
    print("\n❌ FOUND SOFT ERROR HANDLING - FIX THESE NOW")
    sys.exit(1)
else:
    print("✅ No soft error handling found")