#!/bin/bash

# Quick Setup Script for Polymarket Trading System
# Run this script to set up the project quickly

set -e  # Exit on error

echo "╔═══════════════════════════════════════════╗"
echo "║   Polymarket Trading System Setup        ║"
echo "║   Quick Start Script                     ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# Check Python version
echo "➤ Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '(?<=Python )\d+\.\d+')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "✗ Error: Python 3.10+ is required. You have Python $PYTHON_VERSION"
    echo "  Please install Python 3.10 or higher"
    exit 1
fi

echo "✓ Python $PYTHON_VERSION detected"
echo ""

# Create virtual environment
echo "➤ Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠ Virtual environment already exists. Skipping..."
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "➤ Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "➤ Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✓ pip upgraded"
echo ""

# Install requirements
echo "➤ Installing dependencies..."
echo "  This may take a few minutes..."
pip install -r requirements.txt > /dev/null 2>&1
echo "✓ Dependencies installed"
echo ""

# Create .env file if it doesn't exist
echo "➤ Setting up environment file..."
if [ -f ".env" ]; then
    echo "⚠ .env file already exists. Skipping..."
else
    cp .env.example .env
    echo "✓ .env file created from template"
    echo ""
    echo "⚠ IMPORTANT: You need to edit .env with your API credentials!"
    echo "  Run: nano .env"
    echo "  Or: code .env"
fi
echo ""

# Check if git is initialized
echo "➤ Checking git repository..."
if [ -d ".git" ]; then
    echo "✓ Git repository already initialized"
else
    echo "⚠ Git repository not initialized"
    read -p "  Do you want to initialize git? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git init
        git add .
        git commit -m "Initial commit"
        echo "✓ Git repository initialized"
    else
        echo "  Skipped git initialization"
    fi
fi
echo ""

# Display summary
echo "═══════════════════════════════════════════"
echo "           SETUP COMPLETED! ✓              "
echo "═══════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your credentials:"
echo "   nano .env"
echo ""
echo "2. Add your Polymarket API credentials:"
echo "   - POLYMARKET_API_KEY"
echo "   - POLYMARKET_SECRET"
echo "   - POLYMARKET_PRIVATE_KEY"
echo ""
echo "3. Test your setup:"
echo "   python test_setup.py"
echo ""
echo "4. When everything works, start the bot:"
echo "   python main.py"
echo ""
echo "📚 Documentation:"
echo "   - README.md: Full documentation"
echo "   - NEXT_STEPS.md: Detailed development guide"
echo "   - LANGCHAIN_NOTES.md: LangChain integration guide"
echo ""
echo "⚠️  Remember: ALWAYS start in testnet mode!"
echo "   Set USE_TESTNET=true in your .env file"
echo ""
echo "═══════════════════════════════════════════"
