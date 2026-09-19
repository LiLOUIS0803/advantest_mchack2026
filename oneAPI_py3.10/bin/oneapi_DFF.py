#
# Copyright (C) 2022-2025 Advantest Corporation
# All rights reserved.
#
from typing import Callable, Dict
import json
import os
from jsonschema import validate, ValidationError

from liboneAPI import DFFWrite


class DFF:

    # Error codes
    SUCCEED = 0                         # Communication succeed
    COMMON_ERROR = 1                    # Common Error: Errors that are not specifically defined
    TIMEOUT = 2                         # Communication time out
    TARGET_INVALID = 3                  # Target is invalid (AppDescriptor issue)
    CONNECT_FAILED = 4                  # Unable to connect to the target App
    CERTIFICATE_ERROR = 5               # Certificate related errors
    UNKNOWN_LOCATION = 6                # Unknown location
    NOT_SUPPORT = 7                     # not support DFF feature
    SCHEMA_LOAD_FAIL = 101              # Schema file failed to load, maybe it's not in JSON format
    SCHEMA_SAME = 102                   # Schema with same $id has been already registered by this Program
    SCHEMA_REGIST_FAIL = 103            # Schema registration failed, maybe server is down
    SCHEMA_REGISTERED = 104             # Schema with same $id has been already registered by others
    DFF_CONNECTED = 111                 # Properties are valid, and start to upload, does not mean complete
    DFF_PROPERTY_INVALID = 112          # Properties invalid to schema
    DFF_CONNECT_FAIL = 113              # Failed to establish data-upload connection
    DFF_DATA_EMPTY = 114                # Data is empty
    SCHEMA_NOT_REGISTERED = 115         # The process has not successfully registered Schema
    _schema = None            # schema object
    _properties = {}


    @classmethod
    def importSchema(cls, schema_path: str) -> int:
        """
        Load Schema from input JSON file, and register the Schema to AUS
        """
        if not os.path.exists(schema_path):
            print(f"Schema file not found: {schema_path}")
            return cls.SCHEMA_LOAD_FAIL

        schema_string = (lambda path: open(path, 'r', encoding='utf-8').read())(schema_path)
        result = DFFWrite.importSchema(schema_string)
        if result == DFF.SUCCEED: cls._loadSchema(schema_string)
        return result
        
        
    @classmethod
    def regUploadCallback(cls, callback: Callable[[int, Dict[str, str], str], None]):
        """
        register user-defined callback func to receive upload result
        """
        DFFWrite.regUploadCallback(callback)


    @classmethod
    def set(cls, key: str, value: str):
        """
        Set property key-value pairs for subsequent data uploads
        """
        cls._properties[key] = value
        return cls


    @classmethod
    def upload(cls, data) -> int:
        """
        Asynchronous upload data to AUS
        :param data: The data to be uploaded
        :return: An integer representing the status of the initial upload attempt (not the actual result)
        """
        if not data:                      return DFF.DFF_DATA_EMPTY
        if not cls._schema:               return DFF.SCHEMA_NOT_REGISTERED
        if not cls._isValidProperties():  return DFF.DFF_PROPERTY_INVALID
        
        DFFWrite.setProperties(json.dumps(cls._properties))
        result = DFFWrite.upload(data)
        return result


    @classmethod
    def _loadSchema(cls, schema_string):
        try:
            cls._schema = json.loads(schema_string)
            cls._injectDefaults()
        except Exception as e:
            print(f"load schema fail: {str(e)}")


    @classmethod
    def _injectDefaults(cls):
        schema = cls._schema
        properties = cls._properties
        for key, subschema in schema.get("properties", {}).items():
            if "default" in subschema and key not in properties:
                cls._properties[key] = subschema["default"]


    @classmethod
    def _isValidProperties(cls):
        try:
            validate(instance=cls._properties, schema=cls._schema)
            return True
        except ValidationError as e:
            print(str(e))
            return False
        