import json
from pathlib import Path

import numpy as np
import pytest

from tests.algorithm_validation_tests.exareme2.helpers import algorithm_request
from tests.algorithm_validation_tests.exareme2.helpers import get_test_params
from tests.algorithm_validation_tests.exareme2.helpers import parse_response

algorithm_name = "pca"

expected_file = (
    Path(__file__).parent
    / "expected"
    / f"{algorithm_name}_with_transformation_expected.json"
)

COUNT = 0


@pytest.mark.parametrize("test_input, expected", get_test_params(expected_file))
def test_pca_algorithm(test_input, expected):

    response = algorithm_request(algorithm_name, test_input)

    if "errors" in expected:
        assert (
            "Log transformation cannot be applied to non-positive values."
            or "Standardization cannot be applied to column" in str(response.content)
        )
    else:
        result = parse_response(response)
        assert int(result["n_obs"]) == int(expected["n_obs"])
        np.testing.assert_allclose(
            result["eigenvalues"],
            expected["eigen_vals"],
            rtol=1e-7,
            atol=1e-10,
        )
        for u, v in zip(result["eigenvectors"], expected["eigen_vecs"]):
            assert_vectors_are_collinear(u, v)

        print(test_input["test_case_num"])


def assert_vectors_are_collinear(u, v):
    cosine_similarity = np.dot(v, u) / (np.sqrt(np.dot(v, v)) * np.sqrt(np.dot(u, u)))
    np.testing.assert_allclose(abs(cosine_similarity), 1, rtol=1e-7, atol=1e-10)
