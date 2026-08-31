import asyncio
import json
from typing import Optional

import aiohttp

from src.utils.common_utils import handle_verification_code
from src.utils.device_fingerprint import DeviceFingerprint
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DeviceActivator:
    """Device activation manager - fully async."""

    def __init__(self, config_manager):
        """
        Initialize the device activator.
        """
        self.logger = get_logger(__name__)
        self.config_manager = config_manager
        # Use device_fingerprint instance to manage device identity.
        self.device_fingerprint = DeviceFingerprint.get_instance()
        # Ensure device identity is created.
        self._ensure_device_identity()

        # Current activation task.
        self._activation_task: Optional[asyncio.Task] = None

    def _ensure_device_identity(self):
        """
        Ensure device identity exists.
        """
        (
            serial_number,
            hmac_key,
            is_activated,
        ) = self.device_fingerprint.ensure_device_identity()
        self.logger.info(
            "Device identity: serial number: %s, activation status: %s",
            serial_number,
            "active" if is_activated else "inactive",
        )

    def cancel_activation(self):
        """
        Cancel the activation flow.
        """
        if self._activation_task and not self._activation_task.done():
            self.logger.info("Cancelling activation task.")
            self._activation_task.cancel()

    def has_serial_number(self) -> bool:
        """
        Check whether a serial number exists.
        """
        return self.device_fingerprint.has_serial_number()

    def get_serial_number(self) -> str:
        """
        Get the serial number.
        """
        return self.device_fingerprint.get_serial_number()

    def get_hmac_key(self) -> str:
        """
        Get the HMAC key.
        """
        return self.device_fingerprint.get_hmac_key()

    def set_activation_status(self, status: bool) -> bool:
        """
        Set activation status.
        """
        return self.device_fingerprint.set_activation_status(status)

    def is_activated(self) -> bool:
        """
        Check whether the device is activated.
        """
        return self.device_fingerprint.is_activated()

    def generate_hmac(self, challenge: str) -> str:
        """
        Generate a signature using the HMAC key.
        """
        return self.device_fingerprint.generate_hmac(challenge)

    async def process_activation(self, activation_data: dict) -> bool:
        """Process activation flow asynchronously.

        Args:
            activation_data: Activation data dict, must include challenge and code

        Returns:
            bool: Whether activation succeeded
        """
        try:
            # Track current task.
            self._activation_task = asyncio.current_task()

            # Check for activation challenge and verification code.
            if not activation_data.get("challenge"):
                self.logger.error("Activation data missing challenge field.")
                return False

            if not activation_data.get("code"):
                self.logger.error("Activation data missing code field.")
                return False

            challenge = activation_data["challenge"]
            code = activation_data["code"]
            message = activation_data.get(
                "message", "Please enter the verification code at xiaozhi.me"
            )

            # Check serial number.
            if not self.has_serial_number():
                self.logger.error("Device has no serial number; cannot activate.")

                # Use device_fingerprint to generate serial number and HMAC key.
                (
                    serial_number,
                    hmac_key,
                    _,
                ) = self.device_fingerprint.ensure_device_identity()

                if serial_number and hmac_key:
                    self.logger.info("Automatically created serial number and HMAC key.")
                else:
                    self.logger.error("Failed to create serial number or HMAC key.")
                    return False

            # Display activation info to the user.
            self.logger.info(f"Activation prompt: {message}")
            self.logger.info(f"Verification code: {code}")

            # Build and print verification code prompt.
            text = (
                ".Please log in to the control panel to add a device and enter the "
                f"verification code: {' '.join(code)}..."
            )
            print("\n==================")
            print(text)
            print("==================\n")
            handle_verification_code(text)

            # Play the verification code via voice.
            try:
                # Play audio in a non-blocking thread.
                from src.utils.common_utils import play_audio_nonblocking

                play_audio_nonblocking(text)
                self.logger.info("Playing verification code voice prompt.")
            except Exception as e:
                self.logger.error(f"Failed to play verification code audio: {e}")

            # Try to activate the device with the verification code.
            return await self.activate(challenge, code)

        except asyncio.CancelledError:
            self.logger.info("Activation flow canceled.")
            return False

    async def activate(self, challenge: str, code: str = None) -> bool:
        """Run activation flow asynchronously.

        Args:
            challenge: Challenge string from the server
            code: Verification code for retry playback

        Returns:
            bool: Whether activation succeeded
        """
        try:
            # Check serial number.
            serial_number = self.get_serial_number()
            if not serial_number:
                self.logger.error(
                    "Device has no serial number; cannot complete HMAC verification."
                )
                return False

            # Compute HMAC signature.
            hmac_signature = self.generate_hmac(challenge)
            if not hmac_signature:
                self.logger.error("Failed to generate HMAC signature; activation failed.")
                return False

            # Wrap payload to match server expectations.
            payload = {
                "Payload": {
                    "algorithm": "hmac-sha256",
                    "serial_number": serial_number,
                    "challenge": challenge,
                    "hmac": hmac_signature,
                }
            }

            # Get activation URL.
            ota_url = self.config_manager.get_config(
                "SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL"
            )
            if not ota_url:
                self.logger.error("OTA URL configuration not found.")
                return False

            # Ensure URL ends with slash.
            if not ota_url.endswith("/"):
                ota_url += "/"

            activate_url = f"{ota_url}activate"
            self.logger.info(f"Activation URL: {activate_url}")

            # Set request headers.
            headers = {
                "Activation-Version": "2",
                "Device-Id": self.config_manager.get_config("SYSTEM_OPTIONS.DEVICE_ID"),
                "Client-Id": self.config_manager.get_config("SYSTEM_OPTIONS.CLIENT_ID"),
                "Content-Type": "application/json",
            }

            # Log debug info.
            self.logger.debug(f"Headers: {headers}")
            payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
            self.logger.debug(f"Payload: {payload_str}")

            # Retry logic.
            max_retries = 60  # Max wait ~5 minutes.
            retry_interval = 5  # 5-second retry interval.

            error_count = 0
            last_error = None

            # Create aiohttp session with a reasonable timeout.
            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                for attempt in range(max_retries):
                    try:
                        self.logger.info(
                            f"Attempting activation (attempt {attempt + 1}/{max_retries})..."
                        )

                        # Play code on retries (starting from the 2nd attempt).
                        if attempt > 0 and code:
                            try:
                                from src.utils.common_utils import (
                                    play_audio_nonblocking,
                                )

                                text = (
                                    ".Please log in to the control panel to add a "
                                    f"device and enter the verification code: {' '.join(code)}..."
                                )
                                play_audio_nonblocking(text)
                                self.logger.info(f"Retrying verification code playback: {code}")
                            except Exception as e:
                                self.logger.error(
                                    f"Retry verification code playback failed: {e}"
                                )

                        # Send activation request.
                        async with session.post(
                            activate_url, headers=headers, json=payload
                        ) as response:
                            # Read response.
                            response_text = await response.text()

                            # Log full response.
                            self.logger.warning(
                                f"\nActivation response (HTTP {response.status}):"
                            )
                            try:
                                response_json = json.loads(response_text)
                                self.logger.warning(json.dumps(response_json, indent=2))
                            except json.JSONDecodeError:
                                self.logger.warning(response_text)

                            # Check response status.
                            if response.status == 200:
                                # Activation success.
                                self.logger.info("Device activated successfully!")
                                self.set_activation_status(True)
                                return True

                            elif response.status == 202:
                                # Wait for user input.
                                self.logger.info(
                                    "Waiting for user to enter verification code..."
                                )

                                # Cancellable wait.
                                await asyncio.sleep(retry_interval)

                            else:
                                # Handle other errors but continue retrying.
                                error_msg = "Unknown error"
                                try:
                                    error_data = json.loads(response_text)
                                    error_msg = error_data.get(
                                        "error",
                                        f"Unknown error (status: {response.status})",
                                    )
                                except json.JSONDecodeError:
                                    error_msg = (
                                        f"Server error (status: {response.status})"
                                    )

                                # Log error but do not terminate.
                                if error_msg != last_error:
                                    self.logger.warning(
                                        "Server returned: %s; continue waiting for activation.",
                                        error_msg,
                                    )
                                    last_error = error_msg

                                # Count consecutive identical errors.
                                if "Device not found" in error_msg:
                                    error_count += 1
                                    if error_count >= 5 and error_count % 5 == 0:
                                        self.logger.warning(
                                            "\nHint: If the error persists, refresh the page "
                                            "to get a new verification code.\n"
                                        )

                                # Cancellable wait.
                                await asyncio.sleep(retry_interval)

                    except asyncio.CancelledError:
                        # Handle cancellation.
                        self.logger.info("Activation flow canceled.")
                        return False

                    except aiohttp.ClientError as e:
                        self.logger.warning(
                            f"Network request failed: {e}; retrying..."
                        )
                        await asyncio.sleep(retry_interval)

                    except asyncio.TimeoutError as e:
                        self.logger.warning(f"Request timed out: {e}; retrying...")
                        await asyncio.sleep(retry_interval)

                    except Exception as e:
                        # Collect detailed exception info.
                        import traceback

                        error_detail = (
                            str(e) if str(e) else f"{type(e).__name__}: Unknown error"
                        )
                        self.logger.warning(
                            f"Error during activation: {error_detail}; retrying..."
                        )
                        # Log full exception details in debug mode.
                        self.logger.debug(
                            f"Full exception details: {traceback.format_exc()}"
                        )
                        await asyncio.sleep(retry_interval)

            # Reached max retries.
            self.logger.error(
                "Activation failed; reached max retries (%s). Last error: %s",
                max_retries,
                last_error,
            )
            return False

        except asyncio.CancelledError:
            self.logger.info("Activation flow canceled.")
            return False
