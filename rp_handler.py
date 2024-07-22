import runpod


def process_input(input):
    """
    Execute the application code
    """
    name = input['name']
    greeting = f'Hello {name}'

    return {
        "greeting": greeting
    }


# ---------------------------------------------------------------------------- #
#                                RunPod Handler                                #
# ---------------------------------------------------------------------------- #
def handler(event):
    """
    This is the handler function that will be called by RunPod serverless.
    """
    return process_input(event['input'])


if __name__ == '__main__':
    runpod.serverless.start({'handler': handler})