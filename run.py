import sys
import os

# Add src to the Python path
sys.path.insert(0, os.path.abspath('src'))

from charlie.main import main

if __name__ == '__main__':
    main()
