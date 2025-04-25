#!/usr/bin/env python3
import os
import re
import sys


def strip_comments_and_clean(text):
    # Save string literals so we don't touch comments inside them
    literals = {}

    def save_literal(match):
        key = f"__STRING_LITERAL_{len(literals)}__"
        literals[key] = match.group(0)
        return key

    # Save string literals
    text = re.sub(r'(["\'])((?:\\.|(?!\1).)*)\1', save_literal, text)

    # Remove block comments (/**/) - including JSDoc
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)

    # Remove line comments (//) but keep the newline
    text = re.sub(r'//.*?($|\n)', r'\1', text)

    # Restore string literals
    for key, value in literals.items():
        text = text.replace(key, value)

    # Remove whitespace from top of file
    text = text.lstrip('\n\r\t ')

    # Normalize to at most one blank line
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    return text


def fix_closing_braces(text):
    # Remove blank lines between closing braces
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        result.append(lines[i])

        # If current line is a closing brace and there are more lines
        if i < len(lines) - 1 and lines[i].strip() == '}':
            # Look at the next line
            next_line = lines[i + 1]
            # If next line is empty and followed by another closing brace
            if next_line.strip() == '' and i < len(lines) - 2 and lines[i + 2].strip() == '}':
                # Skip the empty line
                i += 1
        i += 1

    return '\n'.join(result)


def convert_indentation(text):
    """
    Converts any indentation pattern to consistent 4-space indentation.
    Works with mixed indentation and is idempotent (can be run multiple times).
    """
    lines = text.split('\n')
    result_lines = []

    # First, detect indent structure by looking at indentation changes
    indent_sizes = []
    prev_indent = 0

    for line in lines:
        if line.strip() == '':  # Skip empty lines for indent detection
            continue

        # Count leading spaces
        current_indent = len(line) - len(line.lstrip())

        # If this line has a different indent than the previous line
        if current_indent > prev_indent:
            # This is a new indent level
            indent_diff = current_indent - prev_indent
            if indent_diff not in indent_sizes:
                indent_sizes.append(indent_diff)

        prev_indent = current_indent

    # If we couldn't detect any clear indentation, use 4 as a fallback
    base_indent = min(indent_sizes) if indent_sizes else 4

    # Now process all lines
    for line in lines:
        if line.strip() == '':  # Preserve empty lines
            result_lines.append(line)
            continue

        # Count leading spaces
        leading_spaces = len(line) - len(line.lstrip())

        # Calculate indent levels - divide by actual indent size
        indent_levels = leading_spaces // base_indent if base_indent > 0 else 0

        # Generate new indentation (4 spaces per level)
        new_indent = ' ' * (indent_levels * 4)

        # Replace the original indentation
        result_lines.append(new_indent + line.lstrip())

    return '\n'.join(result_lines)


def process_js_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        # Strip comments and clean whitespace
        stripped = strip_comments_and_clean(content)

        # Fix closing braces - remove blank lines between them
        fixed_braces = fix_closing_braces(stripped)

        # Convert indentation
        indented = convert_indentation(fixed_braces)

        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(indented)

        print(f"✓ Cleaned: {file_path}")
        sys.stdout.flush()  # Force output to display immediately
    except Exception as e:
        print(f"✗ Error processing {file_path}: {e}")
        sys.stdout.flush()


def find_and_process_js_files(directory):
    count = 0
    print(f"Starting to process JavaScript files in: {directory}")
    sys.stdout.flush()

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.js'):
                file_path = os.path.join(root, file)
                print(f"Processing: {file_path}")
                sys.stdout.flush()  # Force output to display immediately
                process_js_file(file_path)
                count += 1

    print(f"\nProcessed {count} JavaScript files.")
    sys.stdout.flush()


if __name__ == "__main__":
    # if len(sys.argv) != 2:
    #     print("Usage: python clean_js.py <directory>")
    #     sys.exit(1)
    #
    # directory = sys.argv[1]
    # if not os.path.isdir(directory):
    #     print(f"Error: '{directory}' is not a valid directory.")
    #     sys.exit(1)

    directory = 'app/static/js'

    print(f"Recursively processing JavaScript files in: {directory}")
    print("- Removing comments")
    print("- Removing whitespace from top of files")
    print("- Removing blank lines between closing braces")
    print("- Normalizing to at most 1 blank line in a row")
    print("- Converting indentation from 2 to 4 spaces")
    sys.stdout.flush()  # Force output to display immediately

    find_and_process_js_files(directory)