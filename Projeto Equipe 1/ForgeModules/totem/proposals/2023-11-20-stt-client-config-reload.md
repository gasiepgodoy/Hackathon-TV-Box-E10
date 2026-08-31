# Make STT Client Resilient to Dynamic Configuration Changes

## Summary
The `STTClient` reads environment variables and config values only during initialization. If a user modifies STT settings (such as `API_KEY` or `LANGUAGE`) via the Config Manager during runtime, the native STT library will not reflect these changes unless the `STTClient` instance is re-created.

## Problem
In `src/utils/stt_client.py`, the native C library reads environment variables like `GROQ_API_KEY` when initialized. The `STTClient` populates these variables during `__init__`. If the configuration changes dynamically (e.g. via a GUI settings panel or an API call), the C library continues to use the old values.

## Evidence
`src/utils/stt_client.py`:
```python
        # Inject configurations into environment variables for the native STT library
        stt_opts = self._config.get_config("STT_OPTIONS", {})
        if stt_opts.get("API_KEY"):
            os.environ["GROQ_API_KEY"] = stt_opts["API_KEY"]
```
The native `libstt.so` likely calls `getenv("GROQ_API_KEY")` during its internal `curl` execution.

## Proposed Solution
If `libstt.so` reads `getenv` per-request (which it likely does since it's just firing `curl`), we can simply update `os.environ` dynamically before calling `stop_recording_and_transcribe`, or expose a native function `stt_set_config` in `libstt.so` to explicitly pass these parameters instead of relying on environment variables. Given the instruction to avoid modifying C code for now, we can update `STTClient.start_recording()` or `stop_recording()` to re-sync `os.environ` with the latest `ConfigManager` state.

## Benefits
- Better user experience: changes to STT settings take effect immediately.
- Eliminates the need to restart the application when API keys change.

## Trade-offs
- Setting `os.environ` repeatedly is technically thread-unsafe in Python, though the impact might be negligible in this application's event loop model.

## Risks
- Environment variable mutation across threads.

## Estimated Complexity
- Low

## Priority
- Low

## Success Criteria
- Changing the `STT_OPTIONS.LANGUAGE` config correctly translates the next transcribed text without restarting the app.

## Open Questions
- Can we safely modify the C bindings instead to take these parameters as arguments?
