#!/bin/bash
# PDF API Startup Script
# ======================
# This script starts the PDF API server with proper environment setup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting PDF API Server${NC}"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ Error: requirements.txt not found. Please run this script from the pdf-api directory.${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating one...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}📦 Activating virtual environment...${NC}"
source venv/bin/activate

# Install/update dependencies
echo -e "${BLUE}📥 Installing dependencies...${NC}"
pip install -r requirements.txt

# Check if payroll-extractor exists
if [ ! -d "../payroll-extractor" ]; then
    echo -e "${RED}❌ Error: payroll-extractor directory not found. Please ensure it exists in the parent directory.${NC}"
    exit 1
fi

# Start the server
echo -e "${GREEN}🎯 Starting FastAPI server on http://localhost:8000${NC}"
echo -e "${BLUE}📚 API Documentation: http://localhost:8000/docs${NC}"
echo -e "${BLUE}❤️  Health Check: http://localhost:8000/health${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

python api/main.py
