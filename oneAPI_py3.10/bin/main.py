#
# Copyright (C) 2022-2025 Advantest Corporation
# All rights reserved.
#
from oneapi import Interface
from oneapi import AppInfo
from sample import SampleMonitor
# from sample import sendCommand
import signal
import sys
import logging
import os
def quit(signum, frame):
    res = Interface.disconnect()
    if res != 0:
        print(f"Disconnect fail. code = {res}")
    sys.exit()
    
# configure logging function, read level from environment variable
def configure_logging()->None:
    log_level = os.environ.get('ACS_LOG_LEVEL', 'INFO')
    log_file = os.environ.get('ACS_LOG_PATH','')
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        logging.error('Invalid log level: %s', log_level)
        sys.exit()
    if log_file !='':
        logging.basicConfig(filename=log_file, level=numeric_level, format='%(asctime)s - %(levelname)s - %(filename)s(%(lineno)d): %(message)s')
    else:
        logging.basicConfig(level=numeric_level, format='%(asctime)s - %(levelname)s - %(filename)s(%(lineno)d): %(message)s')
    logging.info("log level: %s", log_level)
    
    
    
def main():
    configure_logging()
    myMonitor = SampleMonitor()
    Interface.registerMonitor(myMonitor)

    me = AppInfo()
    me.name = "sample" # Recommend using hostname (hostname = socket.gethostname())
    me.vendor = "adv"
    me.version = "1.0.0"

    NexusDataEnabled = True  # whether to enable Nexus Data Streaming and Control
    TPServiceEnabled = True  # whether to enable TPService for communication with NexusTPI
    res = Interface.connect(me, NexusDataEnabled, TPServiceEnabled)

    if res != 0:
        logging.error(f"Connection request failed to initiate. code = {res}")
        sys.exit()

    logging.info("Connection request initiated successfully.")

    signal.signal(signal.SIGINT, quit)
    signal.signal(signal.SIGTERM, quit)
    
    while True:
        signal.pause()

if __name__ == "__main__":
    main()
