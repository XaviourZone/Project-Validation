# Portable PostgreSQL runtime

Place the PostgreSQL ZIP binary distribution under:

- Windows x64: postgres/portable/windows-x64/bin/
- Linux x64: postgres/portable/linux-x64/bin/

The application does not copy a PostgreSQL data directory between operating
systems. database_manager.py initializes postgres/data locally with initdb and
uses pg_ctl to start/status the server.

The PostgreSQL binaries themselves are deployment artifacts and are not stored
in Git.
