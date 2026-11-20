# Persistence boundary

SQLite + FTS5 is the planned canonical store. No production database is created
by this setup. Add versioned migrations, audit records, and session repositories
in the next increment, together with migration and restart tests.
