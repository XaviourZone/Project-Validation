"""Windows/Linux launcher for the full Validation Router service.

Use this file when starting the Router directly. The production implementation
lives in router/app/main.py.
"""

from app.main import main


if __name__ == "__main__":
    main()
