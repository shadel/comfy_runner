from .inf_serverless import ComfyRunnerServerless
import runpod
from .serverless_tools.input_manager import InputManager

input_m = InputManager("/app/inputs")

def run_wf(workflow_input, file_path_list):

    runner = ComfyRunnerServerless()
    output = runner.predict(
        workflow_input,
        file_path_list,
        stop_server_after_completion=True,
    )
    print("final output: ", output)
    return output

def process_input(runid, input):
    """
    Execute the application code
    """
    wokrflow_json = input['workflow_json']
    workflow_input = input_m.store_workflow(runid, "wf.json", wokrflow_json)
    file_path_list = input['file_path_list']
    output = run_wf(workflow_input, file_path_list)

    return {
        "output": output
    }


# ---------------------------------------------------------------------------- #
#                                RunPod Handler                                #
# ---------------------------------------------------------------------------- #
def handler(event):
    """
    This is the handler function that will be called by RunPod serverless.
    """
    runid = event['runid']
    return process_input(runid, event['input'])


if __name__ == '__main__':
    runpod.serverless.start({'handler': handler})