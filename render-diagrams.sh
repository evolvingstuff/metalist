#!/bin/bash

# Render all Mermaid diagrams to PNG files
# This script converts all .md files in docs/diagrams/ to PNG images

echo "🎨 Rendering Mermaid diagrams to PNG..."

# Create the output directory if it doesn't exist
mkdir -p docs/diagrams/png

# Render each diagram
for file in docs/diagrams/*.md; do
    if [ -f "$file" ]; then
        filename=$(basename "$file" .md)
        echo "📊 Rendering $filename..."
        npx mmdc -i "$file" -o "docs/diagrams/png/${filename}.png"
    fi
done

echo "✅ All diagrams rendered successfully!"
echo "📁 PNG files are in: docs/diagrams/png/"