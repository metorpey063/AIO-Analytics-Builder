#!/bin/bash

# Install AiO Tableau Agent skills to the user's Tableau Agent skills directory

set -e  # Exit on error

SKILLS_DIR="$HOME/Documents/My Tableau Repository (Beta)/Tableau Agent/skills"

# Check if the Tableau Agent skills directory exists
if [ ! -d "$SKILLS_DIR" ]; then
    echo "Error: Tableau Agent skills directory not found at:"
    echo "  $SKILLS_DIR"
    echo ""
    echo "Make sure you have:"
    echo "  1. Installed Tableau Studio"
    echo "  2. Opened Tableau Studio at least once"
    echo "  3. Opened Tableau Agent (Extensions menu)"
    echo ""
    exit 1
fi

# Skills ship next to this script (sidekicks/studio/skills/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SKILLS_SOURCE="$SCRIPT_DIR/skills"

if [ ! -d "$SKILLS_SOURCE" ]; then
    echo "Error: Skills not found at $SKILLS_SOURCE"
    exit 1
fi

echo "Installing AiO Tableau Agent skills..."
echo ""

# Copy aio-story skill
if [ -d "$SKILLS_SOURCE/aio-story" ]; then
    rm -rf "$SKILLS_DIR/aio-story"
    cp -r "$SKILLS_SOURCE/aio-story" "$SKILLS_DIR/aio-story"
    echo "✓ Installed aio-story (builder skill)"
else
    echo "✗ aio-story skill not found at $SKILLS_SOURCE/aio-story"
    exit 1
fi

# Copy aio-audience skill
if [ -d "$SKILLS_SOURCE/aio-audience" ]; then
    rm -rf "$SKILLS_DIR/aio-audience"
    cp -r "$SKILLS_SOURCE/aio-audience" "$SKILLS_DIR/aio-audience"
    echo "✓ Installed aio-audience (interpreter skill)"
else
    echo "✗ aio-audience skill not found at $SKILLS_SOURCE/aio-audience"
    exit 1
fi

# Copy aio-autobuilder skill
if [ -d "$SKILLS_SOURCE/aio-autobuilder" ]; then
    rm -rf "$SKILLS_DIR/aio-autobuilder"
    cp -r "$SKILLS_SOURCE/aio-autobuilder" "$SKILLS_DIR/aio-autobuilder"
    echo "✓ Installed aio-autobuilder (auto-build skill)"
else
    echo "✗ aio-autobuilder skill not found at $SKILLS_SOURCE/aio-autobuilder"
    exit 1
fi

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. In Tableau Agent, type: /reload-skills"
echo "  2. Try the builder skill: 'walk the AiO story' (guided building)"
echo "  3. Try the auto-builder skill: 'build the demo' (auto-create worksheets)"
echo "  4. Try the audience skill: 'explain this chart' (narrative interpretation)"
echo ""

