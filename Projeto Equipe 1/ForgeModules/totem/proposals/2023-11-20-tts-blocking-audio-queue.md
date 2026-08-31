# Improve TTS Audio Queue Concurrency to Prevent Blocking

## Summary
The current `_audio_queue_worker` in `src/utils/common_utils.py` holds the `_audio_lock` for the entire duration of `_play_system_tts(text)` and the subsequent sleep. This prevents any other component from using the audio subsystem efficiently and forces strict sequential processing that can delay time-critical audio feedback.

## Problem
In `src/utils/common_utils.py`, the `_audio_queue_worker` executes:
```python
            with _audio_lock:
                logger.info(f"Starting audio playback: {text[:50]}...")
                success = _play_system_tts(text)
                ...
                time.sleep(0.5)  # Pause after playback to avoid tail clipping.
```
While this ensures sequential playback of system TTS, keeping the lock acquired during the `time.sleep` and the slow, synchronous `subprocess.run` calls within `_play_system_tts` blocks any other thread that might need to acquire `_audio_lock` to check state or enqueue urgent alerts.

## Evidence
- `src/utils/common_utils.py` lines 47-60.
- `subprocess.run` in `_play_linux_tts` and `_play_macos_tts` block the thread synchronously.

## Proposed Solution
Refactor the audio queue worker to release the lock immediately after retrieving the task from the queue or updating internal state, and perform the actual blocking `_play_system_tts` operation and `time.sleep` outside of the `_audio_lock` context. The Queue itself is already thread-safe.

## Benefits
- Increased responsiveness for concurrent audio interruptions or state checks.
- Eliminates potential priority inversions or deadlocks if other components try to acquire `_audio_lock` during playback.

## Trade-offs
- If `_audio_lock` was intended to exclusively serialize hardware access across multiple modules, releasing it too early might cause overlapping audio if another module bypasses the queue. However, all audio is routed through `_audio_queue`.

## Risks
- Unexpected simultaneous audio if external modules use the lock.

## Estimated Complexity
- Low

## Priority
- Medium

## Success Criteria
- Audio queue lock contention is eliminated.

## Open Questions
- Is `_audio_lock` used anywhere else in the codebase outside of `_audio_queue_worker`?
