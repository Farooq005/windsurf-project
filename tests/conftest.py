"""Configuration for pytest."""
import os
import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('../credentials.env')

# Add command line options
def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="run slow tests"
    )
    parser.addoption(
        "--run-integration", action="store_true", default=False, help="run integration tests"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    config.addinivalue_line("markers", "integration: mark test as integration test")

def pytest_collection_modifyitems(config, items):
    skip_slow = not config.getoption("--run-slow")
    skip_integration = not config.getoption("--run-integration")
    
    skip_markers = [
        (skip_slow, "slow", "need --run-slow option to run"),
        (skip_integration, "integration", "need --run-integration option to run")
    ]
    
    for item in items:
        for condition, mark, reason in skip_markers:
            if condition and mark in item.keywords:
                item.add_marker(pytest.mark.skip(reason=reason))
