# Remove Runtime Package Installation via `apt-get`

## Summary

The `DependencyManager` class currently attempts to resolve missing dependencies by automatically running `sudo apt-get install` during the runtime execution of the application. This proposal suggests deprecating runtime automated `apt-get` execution in favor of a documented, operator-friendly setup process to improve system stability and security.

## Problem

In `src/utils/dependency_manager.py`, the method `check_and_install_missing` parses C compilation error logs to identify missing dependencies like `portaudio19-dev` or `libasound2-dev`. If found, it attempts to install them automatically using `sudo apt-get install`.

Running system package managers automatically during runtime poses several issues:
1. **Security Risks:** The application attempts to invoke `sudo` to gain root privileges automatically. In environments where the user is not a sudoer or where `sudo` prompts are strictly managed or blocked in background services, this can cause the process to hang or crash unexpectedly.
2. **Environment Contamination:** The application makes assumptions about the host environment, risking potential conflicts with system libraries or other applications running on the same device.
3. **Implicit Dependencies:** Hidden installations make it difficult to replicate environments consistently across devices and testing environments.

## Evidence

In `src/utils/dependency_manager.py`:
- `is_apt_available` checks for the existence of `apt-get`.
- `check_and_install_missing` maps header errors (like `"portaudio.h": "portaudio19-dev"`) and executes `subprocess.run(["sudo", "apt-get", "install", "-y"] + found_missing, check=True)`.

## Proposed Solution

1. Deprecate and remove the `check_and_install_missing` method and associated `subprocess` calls executing `apt-get` from `src/utils/dependency_manager.py`.
2. Introduce a dedicated setup script (e.g., `scripts/setup_dependencies.sh`) or a clearly documented `Makefile` target (e.g., `make install-deps`) that operators must run manually during project initialization or provisioning.
3. Update the `DependencyManager` to act purely as a diagnostic tool. If missing dependencies are detected during runtime (e.g., failed binary compilation), it should log an explicit error specifying the exact packages that need to be installed manually, without attempting to install them itself.

## Benefits

- **Improved Security:** Eliminates unexpected `sudo` escalations.
- **Predictable Environments:** Enforces declarative dependencies, preventing state drift.
- **Reliability:** Avoids blocking or crashing in headless, non-interactive, or restricted environments.
- **Maintainability:** Standardizes setup and provisioning processes for all developers and operators.

## Trade-offs

- Developers and operators will have to explicitly perform an additional setup step before running the application on a fresh system.
- Initial onboarding time might increase slightly, although documentation will mitigate this.

## Risks

- Some automated testing environments or CI pipelines relying on the automatic runtime installation may temporarily break until the setup phase is updated to include the necessary manual installation commands.

## Estimated Complexity

- Low

## Priority

- Medium

## Success Criteria

- All `sudo apt-get` subprocess calls are removed from the `DependencyManager`.
- System dependencies are explicitly defined and documented in a setup script or README.
- Attempting to run the application with missing native dependencies logs an actionable error message rather than attempting installation.

## Open Questions

- Should we provide setup scripts for package managers other than `apt-get` (e.g., `dnf`, `pacman`, `brew`) for broader OS support?
