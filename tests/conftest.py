import os
import sys

# Must be set before any module is imported — core/config.py reads these at module level
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-anthropic-key')
os.environ.setdefault('BRAVE_API_KEY', 'test-brave-key')
os.environ.setdefault('RAPIDAPI_KEY', 'test-rapidapi-key')

# Add scripts/ to sys.path so subpackages (core, pipeline, sources, etc.) are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
