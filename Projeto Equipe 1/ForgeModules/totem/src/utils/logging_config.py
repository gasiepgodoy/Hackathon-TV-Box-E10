import logging
from logging.handlers import TimedRotatingFileHandler

from colorlog import ColoredFormatter


def setup_logging():
    """
    Configure the logging system.
    """
    from .resource_finder import get_project_root

    # Use resource_finder to get project root and create the logs directory.
    project_root = get_project_root()
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    # Log file path.
    log_file = log_dir / "app.log"

    # Create the root logger.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Set root log level.

    # Clear existing handlers (avoid duplicates).
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Create console handler.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create daily rotating file handler.
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",  # Rotate at midnight.
        interval=1,  # Every day.
        backupCount=30,  # Keep 30 days of logs.
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.suffix = "%Y-%m-%d.log"  # Log file suffix format.

    # Create formatters.
    formatter = logging.Formatter(
        "%(asctime)s[%(name)s] - %(levelname)s - %(message)s - %(threadName)s"
    )

    # Console color formatter.
    color_formatter = ColoredFormatter(
        "%(green)s%(asctime)s%(reset)s[%(blue)s%(name)s%(reset)s] - "
        "%(log_color)s%(levelname)s%(reset)s - %(green)s%(message)s%(reset)s - "
        "%(cyan)s%(threadName)s%(reset)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={"asctime": {"green": "green"}, "name": {"blue": "blue"}},
    )
    console_handler.setFormatter(color_formatter)
    file_handler.setFormatter(formatter)

    # Add handlers to the root logger.
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Log the logging configuration.
    logging.info("Logging initialized, log file: %s", log_file)

    return log_file


def get_logger(name):
    """Get a logger with the shared configuration.

    Args:
        name: Logger name, usually the module name

    Returns:
        logging.Logger: Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("This is an info message")
        logger.error("Error occurred: %s", error_msg)
    """
    logger = logging.getLogger(name)
    return logger
