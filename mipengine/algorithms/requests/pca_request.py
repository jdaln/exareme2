import requests
from mipengine.controller.api.algorithm_request_dto import (
    AlgorithmInputDataDTO,
    AlgorithmRequestDTO,
)

from devtools import debug

def do_post_request():
    url = "http://127.0.0.1:5000/algorithms" + "/pca"

    pathology = "dementia"
    datasets = ["edsd"]
    x = [
        "lefthippocampus",
        "righthippocampus",
        "rightppplanumpolare",
        "leftamygdala",
        "rightamygdala",
    ]
    filters = {
        "condition": "AND",
        "rules": [
            {
                "id": "dataset",
                "type": "string",
                "value": datasets,
                "operator": "in",
            },
            {
                "condition": "AND",
                "rules": [
                    {
                        "id": variable,
                        "type": "string",
                        "operator": "is_not_null",
                        "value": None,
                    }
                    for variable in x
                ],
            },
        ],
        "valid": True,
    }

    algorithm_input_data = AlgorithmInputDataDTO(
        pathology=pathology,
        datasets=datasets,
        filters=filters,
        x=x,
    )

    algorithm_request = AlgorithmRequestDTO(
        inputdata=algorithm_input_data,
        parameters={},
    )

    debug(algorithm_request)
    print(f"POSTing to {url}")

    request_json = algorithm_request.json()

    headers = {"Content-type": "application/json", "Accept": "text/plain"}
    response = requests.post(url, data=request_json, headers=headers)

    return response


if __name__ == "__main__":
    response = do_post_request()
    print(f"\nResponse:")
    print(f"Status code-> {response.status_code}")
    print(f"Algorithm result-> {response.text}")
