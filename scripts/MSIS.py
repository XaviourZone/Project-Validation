"""Standalone MSIS feed.
Edit SOURCE_ID, INPUT, ROUTER, DATABASE and DESTINATION below for deployment.
"""
from scripts.feed_common import FeedRunner

SOURCE_ID = "MSIS"
PARSER_NAME = "MSIS"

INPUT = {
        "type": "FOLDER", "folder": "DATA_INFLOW/MSIS", "pattern": "*.csv", "recursive": true, "poll_seconds": 1.0, "encoding": "utf-8",
}

ROUTER = {
    "enabled": False,
    "host": "127.0.0.1",
    "port": 10001,
    "protocol": "TCP",
    "framing": "LINE",
    "timeout_seconds": 5,
}

DATABASE = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "validation",
    "user": "validation",
    "password": "CHANGE_ME",
}

DESTINATION = {
    "type": "FOLDER",
    "folder": "runtime/xml/pending/MSIS",
}

CONFIG = {
    "SOURCE_ID": SOURCE_ID,
    "PARSER_NAME": PARSER_NAME,
    "INPUT": INPUT,
    "ROUTER": ROUTER,
    "DATABASE": DATABASE,
    "DESTINATION": DESTINATION,
}

if __name__ == "__main__":
    FeedRunner(CONFIG).run()
