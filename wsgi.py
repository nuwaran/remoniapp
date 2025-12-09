"""
WSGI configuration for PythonAnywhere deployment
"""
import sys
import os
from pathlib import Path

# Add project directory to path
project_home = Path(__file__).parent
if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(project_home / '.env')

# Import Flask app
from app import app as application

# Set up logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

if __name__ == "__main__":
    application.run()
