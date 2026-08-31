# -*- coding: utf-8 -*-
import socket
import struct
import time
import asyncio
from typing import Optional
from src.utils.logging_config import get_logger
from src.utils.memory_db import save_setting, get_setting

logger = get_logger(__name__)

def get_ntp_time(host: str = "a.st1.ntp.br") -> Optional[float]:
    """Queries an NTP server for the current network time (Unix timestamp)."""
    msg = bytearray(48)
    msg[0] = 0x1B  # LI = 0 (no warning), VN = 3 (version 3), Mode = 3 (client)
    try:
        addr = socket.getaddrinfo(host, 123)[0][4]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2.0)
            s.sendto(msg, addr)
            msg, _ = s.recvfrom(48)
        
        # Transmit timestamp: bytes 40-43 (seconds), 44-47 (fraction)
        secs = struct.unpack("!I", msg[40:44])[0]
        # NTP epoch is 1900-01-01, Unix epoch is 1970-01-01 (difference: 2208988800s)
        return secs - 2208988800
    except Exception as e:
        logger.debug("Failed to fetch NTP time from %s: %s", host, e)
        return None

async def resolve_ntp_offset() -> float:
    """
    Attempts to sync time with NTP servers.
    Returns offset in seconds (ntp_time - local_time).
    If sync fails, returns the last successfully saved offset from memory.db, or 0.0.
    """
    ntp_servers = ["a.st1.ntp.br", "b.st1.ntp.br", "pool.ntp.org"]
    
    # Try fetching NTP time in a non-blocking thread pool
    loop = asyncio.get_running_loop()
    for server in ntp_servers:
        ntp_time = await loop.run_in_executor(None, get_ntp_time, server)
        if ntp_time is not None:
            offset = ntp_time - time.time()
            logger.info("NTP synchronization successful with %s. Offset: %.3fs", server, offset)
            try:
                save_setting("ntp_offset", str(offset))
            except Exception as e:
                logger.error("Failed to save NTP offset to DB: %s", e)
            return offset
            
    # If NTP query fails, try to load last saved offset
    try:
        saved_offset_str = get_setting("ntp_offset")
        if saved_offset_str is not None:
            offset = float(saved_offset_str)
            logger.info("NTP query failed. Using last saved offset: %.3fs", offset)
            return offset
    except Exception as e:
        logger.error("Failed to read saved NTP offset: %s", e)
        
    logger.warning("NTP synchronization failed and no saved offset found. Using 0.0.")
    return 0.0
