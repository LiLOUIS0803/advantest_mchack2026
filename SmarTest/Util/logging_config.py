import os
import logging
import time

def setup_logging():
    # Create a logger
    logger = logging.getLogger(__name__)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.setLevel(logging.DEBUG)
    # Ensure the logs folder exists
    python_file_path = os.path.abspath(__file__)
    program_path = os.path.dirname(python_file_path)
    # Ensure the logs folder exists
    logs_folder = f'{program_path}/logs'
    if not os.path.exists(logs_folder):
        os.makedirs(logs_folder)

    # Create a unique log file name with a timestamp
    timestamp = time.strftime('%Y%m%d', time.gmtime())
    log_file_name = f'{logs_folder}/PlanExec_{timestamp}.log'

    # Create handlers
    file_handler = logging.FileHandler(log_file_name)
    file_handler.setLevel(logging.INFO)  # Set file handler to INFO level
    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(logging.DEBUG)  # Set stdout handler to DEBUG level

    # Create a formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    # Set the formatter to use UTC time
    formatter.converter = time.gmtime
    file_handler.setFormatter(formatter)
    stdout_handler.setFormatter(formatter)
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(stdout_handler)

    return logger
