# Tests

This directory contains tests for the feudal simulation components and systems.

## Test Files

- **test_entity_system.py** - Tests for the core Entity-Component system
- **test_rookery_system.py** - Tests for the RookeryComponent raven communication system
- **test_simple_raven.py** - Simple focused test for raven delivery debugging

## Running Tests

From the project root directory:

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python tests/test_entity_system.py
python tests/test_rookery_system.py

# Run with verbose output
python tests/test_rookery_system.py -v
```

## Test Organization

Tests are organized by component/system:
- Core system tests (entities, events, config, time)
- Component tests (rookery, AI, movement, etc.)
- Integration tests (full simulation scenarios)

Each test file includes both unit tests and integration scenarios to ensure components work both in isolation and together.