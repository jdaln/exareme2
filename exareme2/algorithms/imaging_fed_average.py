from cgi import log
from functools import reduce
from logging import WARNING
from typing import Any
from typing import List

import numpy as np
import numpy.typing as npt

from exareme2.services.imaging_utilities import ndarrays_to_parameters
from exareme2.services.imaging_utilities import parameters_to_ndarrays

NDArray = npt.NDArray[Any]
NDArrayInt = npt.NDArray[np.int_]
NDArrayFloat = npt.NDArray[np.float_]
NDArrays = List[NDArray]


def aggregate_fit(
    self,
    server_round: int,
    results  #: List[Tuple[ClientProxy, FitRes]],
    # failures, #: List[Union[Tuple[ClientProxy, FitRes], BaseException]],
):  # -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
    """Aggregate fit results using weighted average."""
    if not results:
        return None, {}
    # Do not aggregate if there are failures and failures are not accepted
    if not self.accept_failures and failures:
        return None, {}

    # Convert results
    weights_results = [
        (parameters_to_ndarrays(fit_res.parameters), fit_res.num_examples)
        for _, fit_res in results
    ]
    parameters_aggregated = ndarrays_to_parameters(aggregate(weights_results))

    # Aggregate custom metrics if aggregation fn was provided
    metrics_aggregated = {}
    if self.fit_metrics_aggregation_fn:
        fit_metrics = [(res.num_examples, res.metrics) for _, res in results]
        metrics_aggregated = self.fit_metrics_aggregation_fn(fit_metrics)
    elif server_round == 1:  # Only log this warning once
        log(WARNING, "No fit_metrics_aggregation_fn provided")

    return parameters_aggregated, metrics_aggregated


# def imaging_fed_average(evaluate_fn, fit_round):
def aggregate_evaluate(
    self,
    server_round: int,
    results,  #: List[Tuple[ClientProxy, EvaluateRes]],
    failures,  #: List[Union[Tuple[ClientProxy, EvaluateRes], BaseException]],
):  # -> Tuple[Optional[float], Dict[str, Scalar]]:
    """Aggregate evaluation losses using weighted average."""
    if not results:
        return None, {}
    # Do not aggregate if there are failures and failures are not accepted
    # if not self.accept_failures and failures:
    #     return None, {}

    # Aggregate loss
    loss_aggregated = weighted_loss_avg(
        [(evaluate_res.num_examples, evaluate_res.loss) for _, evaluate_res in results]
    )

    # Aggregate custom metrics if aggregation fn was provided
    metrics_aggregated = {}
    if self.evaluate_metrics_aggregation_fn:
        eval_metrics = [(res.num_examples, res.metrics) for _, res in results]
        metrics_aggregated = self.evaluate_metrics_aggregation_fn(eval_metrics)
    elif server_round == 1:  # Only log this warning once
        log(WARNING, "No evaluate_metrics_aggregation_fn provided")

    return loss_aggregated, metrics_aggregated


# helper functions
def weighted_loss_avg(results):  #: List[Tuple[int, float]]) -> float:
    """Aggregate evaluation results obtained from multiple clients."""
    num_total_evaluation_examples = sum([num_examples for num_examples, _ in results])
    weighted_losses = [num_examples * loss for num_examples, loss in results]
    return sum(weighted_losses) / num_total_evaluation_examples


# : List[Tuple[NDArrays, int]]) -> NDArrays
def aggregate(results):
    """Compute weighted average."""
    # Calculate the total number of examples used during training
    num_examples_total = sum([num_examples for _, num_examples in results])

    # Create a list of weights, each multiplied by the related number of examples
    weighted_weights = [
        [layer * num_examples for layer in weights] for weights, num_examples in results
    ]

    # Compute average weights of each layer
    weights_prime: NDArrays = [
        reduce(np.add, layer_updates) / num_examples_total
        for layer_updates in zip(*weighted_weights)
    ]
    return weights_prime
