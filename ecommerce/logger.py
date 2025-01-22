import logging

# Create and configure logger
logging.basicConfig(
    level=logging.DEBUG,  # Set logging level
    format='%(asctime)s - %(levelname)s - %(message)s',  # Log format
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        logging.StreamHandler()          # Log to the console
    ]
)

# Create a logger instance
logger = logging.getLogger(__name__)

# Example usage
logger.debug("This is a debug message.")
logger.info("This is an info message.")
logger.warning("This is a warning message.")
logger.error("This is an error message.")
logger.critical("This is a critical message.")
