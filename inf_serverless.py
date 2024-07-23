import json
import os
import traceback
import subprocess
from .inf import ComfyRunner
import websocket
import uuid
from git import Repo

from .constants import (
    APP_PORT,
    COMFY_BASE_PATH,
    MODEL_FILETYPES,
    OPTIONAL_MODELS,
    SERVER_ADDR,
)
from .utils.comfy.api import ComfyAPI
from .utils.comfy.methods import ComfyMethod
from .utils.common import (
    clear_directory,
    copy_files,
    find_file_in_directory,
)
from .utils.logger import LoggingType, app_logger


class ComfyRunnerServerless(ComfyRunner):
    def __init__(self):
        super().__init__()

    def get_output(self, ws, prompt, client_id, output_node_ids):
        prompt_id = self.comfy_api.queue_prompt(prompt, client_id)["prompt_id"]

        # waiting for the execution to finish
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break  # Execution is done
            else:
                continue  # previews are binary data

        # fetching results
        history = self.comfy_api.get_history(prompt_id)[prompt_id]
        output_list = {"file_list": [], "text_output": []}
        output_node_ids = [str(id) for id in output_node_ids] if output_node_ids else []
        for node_id in history["outputs"]:
            if (
                output_node_ids and len(output_node_ids) and node_id in output_node_ids
            ) or not output_node_ids:
                node_output = history["outputs"][node_id]
                if "gifs" in node_output:
                    for gif in node_output["gifs"]:
                        output_list["file_list"].append({"filename": gif["filename"], "node_id": node_id})

                if "text" in node_output:
                    for txt in node_output["text"]:
                        output_list["text_output"].append({"text": txt, "node_id": node_id})

                if "images" in node_output:
                    for img in node_output["images"]:
                        output_list["file_list"].append({"filename": img["filename"], "node_id": node_id})

        return output_list

    def predict(
        self,
        workflow_input,
        file_path_list=[],
        extra_models_list=[],
        extra_node_urls=[],  # [{'url': github_url, 'commit_hash': xyz},...]
        stop_server_after_completion=False,
        clear_comfy_logs=True,
        output_folder="./output",
        output_node_ids=None,
        ignore_model_list=[],
        client_id=None,
        comfy_commit_hash=None,
    ):
        """
        workflow_input:                 API json of the workflow. Can be a filepath or str
        file_path_list:                 files to copy inside the '/input' folder which are being used in the workflow
        extra_models_list:              extra models to be downloaded
        extra_node_urls:                extra nodes to be downloaded (with the option to specify commit version)
        stop_server_after_completion:   stop server as soon as inference completes (or fails)
        clear_comfy_logs:               clears the temp comfy logs after every inference
        output_folder:                  for storing inference output
        output_node_ids:                nodes to look in for the output
        ignore_model_list:              these models won't be downloaded (in cases where these are manually placed)
        client_id:                      this can be used as a tag for the generations
        comfy_commit_hash:              specific comfy commit to checkout
        """
        output_list = {}
        try:
            # TODO: add support for image and normal json files
            workflow = self.load_workflow(workflow_input)
            if not workflow:
                app_logger.log(LoggingType.ERROR, "Invalid workflow file")
                return

            # cloning comfy repo
            app_logger.log(LoggingType.DEBUG, "cloning comfy repo")
            comfy_repo_url = "https://github.com/comfyanonymous/ComfyUI"
            comfy_manager_url = "https://github.com/ltdrdata/ComfyUI-Manager"
            if not os.path.exists(COMFY_BASE_PATH):
                comfy_repo = Repo.clone_from(comfy_repo_url, COMFY_BASE_PATH)

            if comfy_commit_hash is not None:
                try:
                    comfy_repo = Repo(COMFY_BASE_PATH)
                    current_hash = comfy_repo.rev_parse("HEAD")
                    if str(current_hash) == comfy_commit_hash:
                        app_logger.log(
                            LoggingType.DEBUG,
                            f"ComfyUI at stable commit hash",
                        )
                    else:
                        app_logger.log(
                            LoggingType.DEBUG,
                            f"Moving ComfyUI to commit {comfy_commit_hash}",
                        )
                        comfy_repo.git.checkout(comfy_commit_hash)
                except Exception as e:
                    print("unable to checkout Comfy, aborting")
                    return None

            if not os.path.exists(COMFY_BASE_PATH + "custom_nodes/ComfyUI-Manager"):
                os.chdir(COMFY_BASE_PATH + "custom_nodes/")
                Repo.clone_from(comfy_manager_url, "ComfyUI-Manager")
                os.chdir("../../")

            # installing requirements
            app_logger.log(
                LoggingType.DEBUG, "Checking comfy requirements, please wait..."
            )
            subprocess.run(
                ["pip", "install", "-r", COMFY_BASE_PATH + "requirements.txt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )

            # clearing the previous logs
            if not self.is_server_running():
                self.clear_comfy_logs()

            # start the comfy server if not already running
            self.start_server()

            # download custom nodes
            res_custom_nodes = self.download_custom_nodes(workflow, extra_node_urls)
            if not res_custom_nodes["status"]:
                app_logger.log(LoggingType.ERROR, res_custom_nodes["message"])
                return

            # download models if not already present
            res_models = self.download_models(
                workflow, extra_models_list, ignore_model_list
            )
            if not res_models["status"]:
                app_logger.log(LoggingType.ERROR, res_models["message"])
                if len(res_models["data"]["models_not_found"]):
                    app_logger.log(
                        LoggingType.INFO,
                        "Please provide custom model urls for the models listed below or modify the workflow json to one of the alternative models listed",
                    )
                    for model in res_models["data"]["models_not_found"]:
                        print("Model: ", model["model"])
                        print("Alternatives: ")
                        if len(model["similar_models"]):
                            for alternative in model["similar_models"]:
                                print(" - ", alternative)
                        else:
                            print(" - None")
                        print("---------------------------")
                return

            # restart the server if custom nodes or models are installed
            if (
                res_custom_nodes["data"]["nodes_installed"]
                or res_models["data"]["models_downloaded"]
            ):
                app_logger.log(LoggingType.INFO, "Restarting the server")
                self.stop_server()
                self.start_server()

            if len(file_path_list):
                clear_directory("./ComfyUI/input")
                for filepath in file_path_list:
                    if isinstance(filepath, str):
                        filepath, dest_path = filepath, "./ComfyUI/input/"
                    else:
                        filepath, dest_path = (
                            filepath["filepath"],
                            "./ComfyUI/input/" + filepath["dest_folder"] + "/",
                        )
                    copy_files(filepath, dest_path, overwrite=True)

            # checkpoints, lora, default etc..
            comfy_directory = COMFY_BASE_PATH + "models/"
            comfy_model_folders = [
                folder
                for folder in os.listdir(comfy_directory)
                if os.path.isdir(os.path.join(comfy_directory, folder))
            ]
            # update model paths e.g. 'v3_sd15_sparsectrl_rgb.ckpt' --> 'SD1.5/animatediff/v3_sd15_sparsectrl_rgb.ckpt'
            for node in workflow:
                if "inputs" in workflow[node]:
                    for key, input in workflow[node]["inputs"].items():
                        if (
                            isinstance(input, str)
                            and any(input.endswith(ft) for ft in MODEL_FILETYPES)
                            and not any(input.endswith(m) for m in OPTIONAL_MODELS)
                        ):
                            base = None
                            # if os.path.sep in input:
                            base, input = os.path.split(input)
                            model_path_list = find_file_in_directory(
                                comfy_directory, input
                            )
                            if len(model_path_list):
                                # selecting the model_path which has the base, if neither has the base then selecting the first one
                                model_path = model_path_list[0]
                                if base:
                                    matching_text_seq = (
                                        ["SD1.5"]
                                        if base in ["SD1.5", "SD1.x"]
                                        else ["SDXL"]
                                    )
                                    for txt in matching_text_seq:
                                        for p in model_path_list:
                                            if txt in p:
                                                model_path = p
                                                break

                                model_path = model_path.replace(comfy_directory, "")
                                if any(
                                    model_path.startswith(folder)
                                    for folder in comfy_model_folders
                                ):
                                    model_path = model_path.split(os.path.sep, 1)[-1]
                                app_logger.log(
                                    LoggingType.DEBUG,
                                    f"Updating {input} to {model_path}",
                                )
                                workflow[node]["inputs"][key] = model_path

            # get the result
            app_logger.log(LoggingType.INFO, "Generating output please wait")
            client_id = client_id or str(uuid.uuid4())
            ws = websocket.WebSocket()
            host = SERVER_ADDR + ":" + str(APP_PORT)
            host = host.replace("http://", "").replace("https://", "")
            ws.connect("ws://{}/ws?clientId={}".format(host, client_id))
            node_output = self.get_output(ws, workflow, client_id, output_node_ids)
            output_list = []
            for file in node_output["file_list"]:
                path = find_file_in_directory("./ComfyUI/output", file["filename"])
                # some intermediary temp files are deleted at this point
                if path:
                    output_list.append({
                        "filename": copy_files(
                            path[0],
                            output_folder,
                            overwrite=False,
                            delete_original=True,
                        ),
                        "node_id": file["node_id"]
                    })
            # print("node output: ", node_output)
            # print("output_list: ", output_list)
            app_logger.log(
                LoggingType.DEBUG, f"output file list len: {len(output_list)}"
            )
            clear_directory("./ComfyUI/output")

            output_list = {
                "file_paths": output_list,
                "text_output": node_output["text_output"],
            }
        except Exception as e:
            app_logger.log(LoggingType.INFO, "Error generating output " + str(e))
            print(traceback.format_exc())

        # stopping the server
        if stop_server_after_completion:
            self.stop_server()

        # TODO: implement a proper way to remove the logs
        if not self.is_server_running() and clear_comfy_logs:
            self.clear_comfy_logs()

        return output_list
          
