

import json
import os
from ..utils.file_downloader import FileDownloader


class InputManager(FileDownloader):
    def __init__(self, input_folder_path):
        super().__init__()
        self.input_folder_path = input_folder_path

    def download_inputs(self, runid, input_files):

        file_paths = []
        
        for input_file in input_files:

            file_path = os.path.join(self.input_folder_path, runid, "files", input_file['filename'])
                    
            _, file_status = self.download_file(
                filename=input_file['filename'],
                url=input_file['url'],
                dest=os.path.join(self.input_folder_path, runid, "files")
            )

            file_paths.append(file_path)
            
        return file_paths
    
    def store_workflow(self, runid, filename, workflow_json): 
        os.makedirs(os.path.join(self.input_folder_path, runid), exist_ok=True)

        workflow_file_path = os.path.join(self.input_folder_path, runid, filename)
        with open(workflow_file_path, "w") as handle:
            json.dump(workflow_json, handle)
        return workflow_file_path
