# Remove Hardcoded Network IP Addresses

## Summary

The codebase currently contains hardcoded IP addresses (specifically `8.8.8.8`) used for checking internet connectivity. This proposal suggests replacing these hardcoded IP addresses with configuration-driven or dynamic hostnames to better support restricted or academic network environments.

## Problem

The project is designed to run in academic environments, such as UNESP Sorocaba, which often have strict firewalls or restrictive proxy rules. Currently, network connectivity checks are performed by attempting to connect to Google's public DNS servers at `8.8.8.8`. In environments where external DNS access is blocked or restricted, these checks will fail, incorrectly reporting an offline status even if the device is connected to a local intranet or proxy-based internet.

## Evidence

The following files contain hardcoded `8.8.8.8` references:
- `main_gui.py` (line 396): Uses `8.8.8.8` in an internet ping check loop.
- `tts_api/main.py` (line 56): Uses `8.8.8.8` to resolve local IP addresses.

Additionally, the project guidelines explicitly forbid hardcoded external network IP addresses to support restricted environments.

## Proposed Solution

Replace the hardcoded `8.8.8.8` IPs with a more robust and flexible approach:
1. Introduce a configurable setting (e.g., `NETWORK.CONNECTIVITY_CHECK_HOST`) via `.env` or `config.json` that administrators can adjust based on their network.
2. For internal IP discovery (as in `tts_api/main.py`), utilize Python's `socket.gethostname()` combined with `socket.gethostbyname()` or rely on local loopback configuration, avoiding external dependencies entirely.
3. Fallback to a well-known academic or internal server if external DNS is unreachable but local network functionality remains.

## Benefits

- **Reliability:** Prevents false offline status reports in restricted networks.
- **Maintainability:** Operators can configure connectivity checks without changing source code.
- **Compliance:** Adheres to the established requirement forbidding hardcoded IPs.

## Trade-offs

- Requires a slight increase in configuration complexity for operators.
- Connecting to hostnames instead of raw IPs adds a DNS resolution step which may take slightly longer in poor network conditions.

## Risks

- If the configurable check host is not set correctly by an operator, the connectivity loop may throw exceptions or fail.
- Changing internal IP discovery logic might introduce slight variations across different OS platforms.

## Estimated Complexity

- Low

## Priority

- High

## Success Criteria

- All references to `8.8.8.8` are removed from the codebase.
- The `ping()` check in `main_gui.py` successfully utilizes a configurable hostname.
- Local IP detection in `tts_api/main.py` functions without relying on external servers.

## Open Questions

- What should be the default hostname or IP used for the connectivity check if none is configured? (e.g., a well-known reliable host like `1.1.1.1` or a UNESP internal server).
