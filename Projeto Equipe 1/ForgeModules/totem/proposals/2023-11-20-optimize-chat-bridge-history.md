# Improve Chat History Management Reliability in Fallback Scenarios

## Summary
The current Chat Bridge component leaves an edge case unhandled when falling back from a primary LLM backend to a secondary backend during a Rate Limit error (429), potentially causing duplicated user prompts in the conversation history.

## Problem
In `src/utils/chat_bridge.py`, the `_build_messages` method appends the user prompt to the `self._history` list. If an API request to the primary backend fails with a 429 error, the exception handler catches it and attempts to use a fallback backend. However, if the primary backend used the binary stream (which uses `_send_and_stream_binary` but `_send_and_stream_binary` does not append to history directly), wait, `_build_messages` is called inside `_stream_api_request`. If the failure happens *during* `_stream_api_request`, the user prompt is already appended. The fallback logic attempts to pop it, but this logic is brittle and only applies if the primary backend was a non-binary backend.

## Evidence
In `src/utils/chat_bridge.py`:
```python
                        if self._history and self._history[-1]["role"] == "user" and self._history[-1]["content"] == prompt:
                            self._history.pop()
```
This cleanup only occurs inside the `send_and_stream` exception handler. If a transient error other than 429 occurs, the history might be left in an inconsistent state (user prompt appended without an assistant response).

## Proposed Solution
Refactor history management so that the user prompt is appended *temporarily* for the request, and only permanently added to `self._history` once the request completes successfully, similar to how the assistant's response is appended at the end of the method.

## Benefits
- More robust history management.
- Prevents duplication of user prompts in history during retries or fallbacks.
- Simplifies fallback logic.

## Trade-offs
- Slight refactoring of `_build_messages` is required.

## Risks
- Regression in conversation flow if history is accidentally not appended on success.

## Estimated Complexity
- Low

## Priority
- Low

## Success Criteria
- Injected network failures do not corrupt the conversation history.

## Open Questions
- Should we also persist conversation history to `memory.db` for long-term recall?
