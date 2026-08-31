# -*- coding: utf-8 -*-
import sys
import os
import time

# Ensure src is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.ntp_sync import get_ntp_time, resolve_ntp_offset
from src.utils.memory_db import init_db, save_setting, get_setting

def test_ntp_flow():
    print("Testing NTP sync helpers...")
    
    # Initialize DB for settings
    init_db()
    
    # 1. Test get_ntp_time directly
    print("Querying public NTP server a.st1.ntp.br...")
    t = get_ntp_time("a.st1.ntp.br")
    if t is not None:
        print(f"Success! NTP Unix Time: {t} (Current local time: {time.time()})")
        assert isinstance(t, float) or isinstance(t, int)
    else:
        print("NTP query timed out or failed (expected if offline).")
        
    # 2. Test DB persistence helpers
    print("Testing save/get settings in memory.db...")
    save_setting("test_key", "test_value")
    val = get_setting("test_key")
    assert val == "test_value", f"Expected 'test_value', got {val}"
    print("DB settings persistence: OK!")
    
    # 3. Test resolve_ntp_offset
    print("Resolving NTP offset...")
    import asyncio
    offset = asyncio.run(resolve_ntp_offset())
    print(f"Resolved offset: {offset}s")
    assert isinstance(offset, float)
    
    # Check if offset was persisted in settings DB
    saved_offset = get_setting("ntp_offset")
    assert saved_offset is not None, "Offset should have been persisted in settings table!"
    print(f"Persisted offset retrieved: {saved_offset}s")
    print("resolve_ntp_offset: OK!")
    
    print("NTP Sync tests: ALL PASSED!")

if __name__ == "__main__":
    test_ntp_flow()
