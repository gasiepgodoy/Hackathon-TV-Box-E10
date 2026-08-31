import subprocess
import logging

logger = logging.getLogger(__name__)

class DependencyManager:
    """
    Handles automatic detection and installation of system dependencies.
    """
    
    DEPS = {
        "curl/curl.h": "libcurl4-openssl-dev",
        "portaudio.h": "portaudio19-dev",
        "cjson/cJSON.h": "libcjson-dev",
        "alsa/asoundlib.h": "libasound2-dev"
    }

    @staticmethod
    def is_apt_available() -> bool:
        """Checks if apt-get is available on the system."""
        try:
            subprocess.run(["apt-get", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def check_and_install_missing(self, error_message: str) -> bool:
        """
        Parses a compilation error message for missing headers and attempts to install them.
        Returns True if an installation was attempted.
        """
        if not self.is_apt_available():
            logger.error("System dependency detection: 'apt' is not available. Please install dependencies manually.")
            return False

        found_missing = []
        for header, package in self.DEPS.items():
            if header in error_message:
                found_missing.append(package)

        if not found_missing:
            return False

        logger.warning(f"Detected missing system dependencies: {', '.join(found_missing)}")
        
        # In a real environment, we'd need sudo. 
        # We will attempt to run with sudo and let the user handle the password prompt in the terminal.
        try:
            print(f"\n[Mina AI] Attempting to install missing dependencies: {' '.join(found_missing)}")
            print("[Mina AI] You may be prompted for your sudo password.")
            
            # Update first
            subprocess.run(["sudo", "apt-get", "update"], check=True)
            
            # Install
            cmd = ["sudo", "apt-get", "install", "-y"] + found_missing
            subprocess.run(cmd, check=True)
            
            logger.info("Successfully installed missing dependencies.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            print(f"\n[Mina AI] Error: Could not install dependencies automatically.")
            print(f"[Mina AI] Please run manually: sudo apt-get install {' '.join(found_missing)}")
            return False

dependency_manager = DependencyManager()
