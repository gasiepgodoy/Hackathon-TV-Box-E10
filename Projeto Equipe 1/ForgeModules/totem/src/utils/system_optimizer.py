import os
import sys
import logging

logger = logging.getLogger(__name__)

def optimize_system():
    """
    Optimize system process priority, CPU affinity, and verification.
    Specifically tuned for Linux (Orange Pi PC Quad-core H3).
    """
    if sys.platform != "linux":
        logger.info("System optimization skipped: Not running on Linux.")
        return

    # 1. Set Process Priority (Nice level)
    try:
        # Lower nice value means higher priority. Root can set negative values (up to -20).
        os.nice(-15)
        logger.info("Process scheduling priority set to high (nice=-15).")
    except PermissionError:
        logger.warning("Unable to set process priority (nice). Run as root to enable high priority.")
    except Exception as e:
        logger.error(f"Failed to set nice level: {e}")

    # 2. CPU Affinity
    try:
        # Guarantee process has access to all 4 CPU cores
        os.sched_setaffinity(0, {0, 1, 2, 3})
        logger.info("CPU affinity successfully mapped to all 4 system cores.")
    except AttributeError:
        # sched_setaffinity not available on this platform/python build
        pass
    except Exception as e:
        logger.error(f"Failed to set CPU affinity: {e}")

    # 3. Verify /tmp mount type
    try:
        if os.path.exists("/proc/mounts"):
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
            if "/tmp" in mounts and "tmpfs" in mounts:
                logger.info("/tmp is mounted on tmpfs (RAM disk). Temporary audio writes are fully optimized.")
            else:
                logger.warning("/tmp is NOT mounted on tmpfs. SD card write latency may degrade speech performance.")
    except Exception as e:
        logger.warning(f"Unable to verify /tmp tmpfs mount: {e}")
