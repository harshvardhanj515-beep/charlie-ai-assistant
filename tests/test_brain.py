import pytest
from charlie.core.settings import WAKE_WORD

def test_wake_word_setting():
    """Ensure the wake word is correctly configured."""
    assert WAKE_WORD == "hey_jarvis", "Wake word configuration is broken"

def test_imports():
    """Ensure core modules can be imported without crashing."""
    try:
        from charlie.modules.brain_module import get_brain
        from charlie.modules.tts_module import get_tts_engine
        success = True
    except ImportError:
        success = False
    assert success, "Failed to import core charlie modules"
