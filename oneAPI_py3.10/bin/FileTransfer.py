import paramiko
import logging
import os
#from AdvantestLogging import logger


class FileTransfer:

    def __init__(self,):
        self._host = None
        self._username = None
        self._password = None
        self._port = None
        self._dirPath = None
        self._transport = None
        self._sftp = None
        self._timeout = 60 # timeout in seconds
        #self.logger = logger

    # initilize host, username, password, port
    def initConfig(self, host=None, username=None, password=None, port=None):

        #read from environment variable
        if host is None:
            host = os.environ.get('ACS_SFTP_HOST', '')
        if username is None:
            username = os.environ.get('ACS_SFTP_USERNAME', '')
        if password is None:
            password = os.environ.get('ACS_SFTP_PASSWORD', '')
        if port is None:
            port = os.environ.get('ACS_SFTP_PORT', 22)
        
        self._host = host
        self._username = username
        self._password = password
        self._port = port
        logging.info("sftp host: %s, username: %s", self._host, self._username)
        logging.debug("sftp password: %s, port: %s", self._password, self._port)

    def connect(self):
        transport = paramiko.Transport((self._host, self._port))
        transport.sock.settimeout(self._timeout)
        transport.connect(username=self._username, password=self._password)
        self._transport = transport
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)

    def disconnect(self):
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None

    def upload(self, local_path, remote_file_name):
        if self._sftp is None:
            logging.error("SFTP connection not established.")
            return False
        remoteFile = os.path.join(self._dirPath, remote_file_name)
        logging.info("Uploading file to %s", remoteFile)
        if not os.path.isfile(local_path):
            logging.error("Local file %s does not exist or is not a regular file", local_path)
            return False
        try:
            self._sftp.put(local_path, remoteFile)
            logging.info("File uploaded successfully to %s", remoteFile)
            return True
        except Exception as e:
            logging.error("Failed to upload %s to %s: %s", local_path, remoteFile, str(e))
            return False
        
    def upload_folder(self, local_dir):
        try:
            # generate the root directory
            root_path = os.path.join(self._dirPath, os.path.basename(local_dir))
            try:
                self._sftp.mkdir(root_path)
            except IOError:
                pass
            # scan local directory and upload files
            for root, dirs, files in os.walk(local_dir):
                # create remote child directories
                remote_path = root_path + root[len(local_dir):]
                for dir_name in dirs:
                    dir_path = os.path.join(remote_path, dir_name).replace("\\", "/")
                    try:
                        self._sftp.mkdir(dir_path)
                    except IOError:
                        pass
                # upload files
                for file_name in files:
                    local_file = os.path.join(root, file_name)
                    if os.path.isfile(local_file):
                        remote_file = os.path.join(remote_path, file_name).replace("\\", "/")
                        self._sftp.put(local_file, remote_file)
                    else:
                        logging.error("file %s is not a file", local_file)
            return True
        except Exception as e:
            logging.error("Failed to upload %s: %s", local_dir, str(e))
            return False
    
    def download(self, localFile, remoteFile:str):
        try:
            if self._sftp is None:
                raise Exception("Not connected")
            
            print(f"local Path: {localFile} remote File: {remoteFile}")
            self._sftp.get(remoteFile, localFile)
            print(f"download {remoteFile} Success")

        except Exception as e:
            logging.error("Failed to download %s: %s", remoteFile, str(e))

    def listdir(self, remote_path):
        if self._sftp is None:
            raise Exception("Not connected")
        return self._sftp.listdir(remote_path)
