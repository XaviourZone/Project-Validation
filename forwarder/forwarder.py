"""Windows/Linux launcher for the full Validation Forwarder service.

Use this file when starting the Forwarder directly. The production implementation
lives in forwarder/app/main.py.
"""

from app.main import main


if __name__ == "__main__":
    main()
