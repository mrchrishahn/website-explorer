#!/bin/zsh

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Setting up website crawler environment...${NC}\n"

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo -e "${BLUE}Installing Homebrew...${NC}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo -e "${GREEN}Homebrew is already installed${NC}"
fi

# Install Python 3.13 with Tkinter support
echo -e "\n${BLUE}Installing Python 3.13 with Tkinter support...${NC}"
brew install python@3.13
brew install python-tk@3.13

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo -e "\n${BLUE}Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo -e "${GREEN}uv is already installed${NC}"
fi

# Create and activate virtual environment
echo -e "\n${BLUE}Creating virtual environment...${NC}"
uv venv .venv
source .venv/bin/activate

# Install Python dependencies
echo -e "\n${BLUE}Installing Python dependencies...${NC}"
uv pip install -r requirements.txt

# Install Playwright browsers
echo -e "\n${BLUE}Installing Playwright browsers...${NC}"
playwright install chromium

# Create necessary directories
echo -e "\n${BLUE}Creating necessary directories...${NC}"
mkdir -p crawling_results

# Create domains.csv if it doesn't exist
if [ ! -f domains.csv ]; then
    echo -e "\n${BLUE}Creating domains.csv template...${NC}"
    echo "example.com" > domains.csv
    echo -e "${GREEN}Created domains.csv template. Please edit it with your target domains.${NC}"
fi

echo -e "\n${GREEN}Setup completed successfully!${NC}"
echo -e "\nTo start crawling:"
echo -e "1. Edit domains.csv with your target domains"
echo -e "2. Run: ${BLUE}source .venv/bin/activate${NC}"
echo -e "3. Run: ${BLUE}python main.py${NC}" 