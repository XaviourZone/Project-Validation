"""Windows/Linux launcher for the full Validation Parser service.

Use this file when starting the Parser directly. The production implementation
lives in parser/app/main.py.
"""

from app.main import main


if __name__ == "__main__":
    main()
