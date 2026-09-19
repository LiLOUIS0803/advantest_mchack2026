#
# Copyright (C) 2022-2025 Advantest Corporation
# All rights reserved.
#
import logging
import datetime
import pytz
import json
import os

__version__ = "1.0.2"

# Custom Formatter class for formatting log records as JSON strings.
class AdvantestFormatter(logging.Formatter):
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger

    # Convert a datetime object to a Unix timestamp (seconds since epoch) in string format.
    def formatTimestamp(self, date):
        return str(int(date.astimezone(pytz.utc).timestamp()))

    # Custom formatting method for log records.
    def format(self, record):
        # Check if it's an AdvantestEventRecord (event log) or regular log.
        if isinstance(record, AdvantestEventRecord):
            data = {
                "testerId": getattr(self.logger, "testerId", ""),     # Tester ID from the event log (if available)
                "edgeServerId": getattr(self.logger, "edgeServerId", ""), # Application instance from the logger (if available)
                "applicationId": getattr(self.logger, "applicationId", ""),           # Application name from the logger (if available)
                "timestamp": self.formatTimestamp(datetime.datetime.now()),  # Current timestamp in Unix format
                "eventType": record.levelname,    # Event log type (e.g., INFO, WARNING, etc.)
                "eventName": record.logname,          # Event log name 
                "message": record.msg,
            }
        else:
            data = {
                "testerId": getattr(self.logger, "testerId", ""),     # Tester ID from the event log (if available)
                "edgeServerId": getattr(self.logger, "edgeServerId", ""), # Application instance from the logger (if available)
                "applicationId": getattr(self.logger, "applicationId", ""),           # Application name from the logger (if available)
                "timestamp": self.formatTimestamp(datetime.datetime.now()),  # Current timestamp in Unix format
                "level": record.levelname,     # Regular log level (e.g., INFO, WARNING, etc.)
                "message": record.msg,         # Regular log message
            }
        if hasattr(record, "custom_labels"):
            data.update(record.custom_labels)
        # Convert the data dictionary to a JSON string and return it.
        return json.dumps(data)

# Custom Logger class to handle application-specific logging.
class AdvantestLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET, applicationId="", edgeServerId="", testerId=""):
        # Call the constructor of the parent class (logging.Logger).
        super().__init__(name, level)
        self.setLevel(level)
        if edgeServerId == "":
            # get env instance if no input instance
            edgeServerId = os.environ.get("EDGE_ID")
            if edgeServerId == "":
                print(f"{edgeServerId} does not exist in the environment.")
        if testerId == "":
            # get env instance if no input instance
            testerId = os.environ.get("TESTER_ID")
            if testerId == "":
                print(f"{testerId} does not exist in the environment.")
        # Store the application and instance names as attributes for the logger.
        self.applicationId = applicationId
        self.edgeServerId = edgeServerId
        self.testerId = testerId

        # Create a custom formatter and add a console handler to log to the console.
        formatter = AdvantestFormatter(logger=self)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)

        file_path = os.environ.get("LOG_FILE_PATH")
        if file_path:
            file_handler = logging.FileHandler(file_path)
            file_handler.setFormatter(formatter)
            self.addHandler(file_handler)
        else:
            # Handle missing FILE_PATH environment variable
            error_handler = logging.StreamHandler()
            error_handler.setLevel(logging.ERROR)
            error_formatter = logging.Formatter("ERROR: LOG_FILE_PATH environment variable is missing.")
            error_handler.setFormatter(error_formatter)
            self.addHandler(error_handler)
class AdvantestEventRecord(logging.LogRecord):
    def __init__(self, level, msg, eventname, *args, **kwargs):
        super().__init__(level, level, "", 0, msg, args, exc_info=None, **kwargs)
        self.logname = eventname
        self.testerId = kwargs.get("testerId", "")

class AdvantestEvent(logging.Logger):
    def __init__(self, name, level=logging.INFO, applicationId="", edgeServerId="", testerId=""):
        super().__init__(name, level)
        self.setLevel(level)
        if edgeServerId == "":
            # get env instance if no input instance
            edgeServerId = os.environ.get("EDGE_ID")
            if edgeServerId == "":
                print(f"{edgeServerId} does not exist in the environment.")
        if testerId == "":
            # get env instance if no input instance
            testerId = os.environ.get("TESTER_ID")
            if testerId == "":
                print(f"{testerId} does not exist in the environment.")
        self.applicationId = applicationId
        self.edgeServerId = edgeServerId
        self.testerId = testerId
        formatter = AdvantestFormatter(logger=self)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)
        file_path = os.environ.get("LOG_FILE_PATH")
        if file_path:
            file_handler = logging.FileHandler(file_path)
            file_handler.setFormatter(formatter)
            self.addHandler(file_handler)
        else:
            # Handle missing FILE_PATH environment variable
            error_handler = logging.StreamHandler()
            error_handler.setLevel(logging.ERROR)
            error_formatter = logging.Formatter("ERROR: LOG_FILE_PATH environment variable is missing.")
            error_handler.setFormatter(error_formatter)
            self.addHandler(error_handler)

    def event(self, eventname, msg, level=logging.INFO, custom_labels=None):
        event_record = AdvantestEventRecord(level, msg, eventname, testerId=self.testerId)
        if custom_labels is not None:
            event_record.custom_labels = custom_labels
        self.handle(event_record)

class Result(logging.Logger):
    def __init__(self, name, level=logging.NOTSET, applicationId="", edgeServerId="", testerId=""):
        super().__init__(name, level)
        self.setLevel(level)
        self.applicationId = applicationId
        if edgeServerId == "":
            # get env instance if no input instance
            edgeServerId = os.environ.get("EDGE_ID")
            if edgeServerId == "":
                print(f"{edgeServerId} does not exist in the environment.")
        if testerId == "":
            # get env instance if no input instance
            testerId = os.environ.get("TESTER_ID")
            if testerId == "":
                print(f"{testerId} does not exist in the environment.")
        self.edgeServerId = edgeServerId
        self.testerId = testerId

        formatter = ResultFormatter(logger=self)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)
        file_path = os.environ.get("RESULT_FILE_PATH")
        if file_path:
            file_handler = logging.FileHandler(file_path)
            file_handler.setFormatter(formatter)
            self.addHandler(file_handler)
        else:
            # Handle missing FILE_PATH environment variable
            error_handler = logging.StreamHandler()
            error_handler.setLevel(logging.ERROR)
            error_formatter = logging.Formatter("ERROR: RESULT_FILE_PATH environment variable is missing.")
            error_handler.setFormatter(error_formatter)
            self.addHandler(error_handler)

class ResultFormatter(logging.Formatter):
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger

    def formatTimestamp(self, date):
        return str(int(date.astimezone(pytz.utc).timestamp()))

    def format(self, record):
        data = {
            "testerId": getattr(self.logger, "testerId", ""),
            "edgeServerId": getattr(self.logger, "edgeServerId", ""),
            "applicationId": getattr(self.logger, "applicationId", ""),
            "timestamp": self.formatTimestamp(datetime.datetime.now()),
            "key": record.msg,
            "value": record.value,
        }

        return json.dumps(data)

class ResultRecord(logging.LogRecord):
    def __init__(self, level, msg, value, *args, **kwargs):
        super().__init__(level, level, "", 0, msg, args, exc_info=None, **kwargs)
        self.value = value

class AdvantestResult(Result):
    def __init__(self, name, level=logging.NOTSET, applicationId="", edgeServerId="", testerId=""):
        super().__init__(name, level, applicationId, edgeServerId, testerId)

    def log_result(self, key, value):
        result_record = ResultRecord(logging.INFO, key, value, testerId=self.testerId)
        self.handle(result_record)
