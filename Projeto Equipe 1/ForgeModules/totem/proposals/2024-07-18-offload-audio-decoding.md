# Offload Synchronous Audio Decoding to Background Worker

## Summary

The `miniaudio.decode` function in `src/utils/tts_client.py` performs CPU-bound audio decoding synchronously on the main asyncio event loop, causing blocking and potential jitter in the voice interface application.

## Problem

When the voice interface receives audio chunks to play via TTS, it decodes them using `miniaudio.decode()`. This is a synchronous, CPU-bound operation. Since it is called directly within the `async def play()` method (in `src/utils/tts_client.py`), it blocks the single-threaded asyncio event loop. If the chunk is large or if there are multiple chunks to process quickly, this can delay the processing of other concurrent tasks (like UI updates in the PyQt GUI, network operations, or wake word listening), leading to a degraded user experience, such as audio stutters or UI freezing.

## Evidence

In `src/utils/tts_client.py`, lines 243-249:
```python
    async def play(self, audio_bytes: bytes, on_start: Optional[Callable] = None) -> None:
        """Play MP3 bytes through the persistent output device (0ms latency, no cutoff)."""
        if not _HAS_MINIAUDIO or not audio_bytes:
            return
        async with self._audio_lock:
            try:
                decoded = miniaudio.decode(audio_bytes, output_format=miniaudio.SampleFormat.SIGNED16)
```
The method is an `async def`, but it calls a regular, synchronous function `miniaudio.decode` directly.

According to the memory:
> To prevent blocking the asyncio event loop, synchronous CPU-bound operations, such as audio decoding with `miniaudio.decode`, should be offloaded to a background worker thread using `asyncio.to_thread`.

## Proposed Solution

Offload the synchronous decoding operation using `asyncio.to_thread` to run it in a background thread, preventing it from blocking the main asyncio event loop.

Change the decoding line to:
```python
decoded = await asyncio.to_thread(miniaudio.decode, audio_bytes, output_format=miniaudio.SampleFormat.SIGNED16)
```
Or use an executor if `asyncio.to_thread` is not available in older Python versions, though `to_thread` is available in Python 3.9+.

## Benefits

- **Performance:** Prevents the main asyncio event loop from stalling during audio decoding.
- **Responsiveness:** Improves the responsiveness of the GUI and other asynchronous tasks running concurrently.
- **Reliability:** Reduces the likelihood of missed events or audio stutters caused by a blocked event loop.

## Trade-offs

- **Overhead:** Introduces a slight overhead for thread context switching and scheduling the task in a thread pool, though this is negligible compared to the benefits of a non-blocking loop.

## Risks

- **Concurrency:** Ensure that `miniaudio.decode` is thread-safe. Given it's a stateless decoding function operating on raw bytes, it is generally thread-safe, but if it relies on any global state, this could be an issue.
- **GIL Contention:** Python's Global Interpreter Lock (GIL) might still cause some contention if the underlying C extension doesn't release the GIL during decoding. However, offloading it to a thread is still better than running it on the main thread for overall responsiveness.

## Estimated Complexity
- Low

## Priority
- High

## Success Criteria

- The voice interface application maintains smooth UI and uninterrupted audio playback.
- The asyncio event loop latency (if measured) remains low during audio synthesis and playback.

## Open Questions

- Does the `miniaudio` python package release the GIL during its decode operation? (If not, the thread offload might still cause some main thread blocking, although it's the standard way to handle CPU-bound tasks in asyncio).