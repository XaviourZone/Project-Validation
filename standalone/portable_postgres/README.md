# Portable PostgreSQL

Supply PostgreSQL binaries separately for Windows x64 and Linux x64.
Do not share a PostgreSQL data directory between operating systems.
Each OS initializes its own cluster with initdb and starts/stops it with pg_ctl.
Default port: 5432.

Expected: windows-x64/bin, linux-x64/bin, data (generated locally), start/stop scripts.
