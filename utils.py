import json
import logging
import os

def load_credentials():
    """Load credentials from JSON file."""
    # Look for credentials.json in the current directory or a parent directory
    possible_paths = [
        'credentials.json',
        os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    logging.info(f"Loading credentials from {path}")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error reading credentials file at {path}: {e}")
                return {} # Return empty dict on error

    logging.warning(
        "credentials.json not found in any expected location. "
        "Please create it in the root directory of the project."
    )
    return {}
