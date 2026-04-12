# Development & Refactoring Scripts

This folder contains temporary scripts, inline execution tests, and refactoring utilities that were used during the development and stabilization phases of the project. 

## Contents
- `db_test.py` / `debug_file.py`: SQLite debugging tools to check database schemas and content (e.g. `workflow_registry`, `file_registry`).
- `parse_test.py`: Standalone document parser tests for PDF and VLM extraction.
- `refactor_*.py`: Automated Python scripts used to apply multi-file data structures across the repository (`fastapi_app.py`, `registry.py`, `worker.py`, etc.).
- `fix_tests.py`: Scripts previously used to patch test files en masse for architectural changes.

These scripts are strictly for internal maintenance, testing, and migration reference. They do not run in the production logic.
