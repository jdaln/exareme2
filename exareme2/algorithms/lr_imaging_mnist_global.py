from typing import Dict

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from exareme2.algorithms.imaging_fed_average import imaging_fed_average
from exareme2.services import imaging_utilities as utils


def fit_round(server_round: int) -> Dict:
    """Send round number to client."""
    return {"server_round": server_round}


def get_evaluate_fn(model: LogisticRegression):
    """Return an evaluation function for server-side evaluation."""

    # Load test data here to avoid the overhead of doing it in `evaluate` itself
    _, (X_test, y_test) = utils.load_mnist()

    # The `evaluate` function will be called after every round
    def evaluate(server_round, parameters, config):
        # Update model with the latest parameters
        utils.set_model_params(model, parameters)
        loss = log_loss(y_test, model.predict_proba(X_test))
        accuracy = model.score(X_test, y_test)
        if server_round > 0:
            server_round -= 1
        return loss, {"accuracy": accuracy}, server_round

    return evaluate


# Start Flower server for five rounds of federated learning
class LRImagingGlobal:

    if __name__ == "__main__":
        model = LogisticRegression()
        utils.set_initial_params(model)
        strategy = imaging_fed_average(
            evaluate_fn=get_evaluate_fn(model), fit_round=fit_round(server_round=5)
        )

    def __init__(self):
        self.strategy = None

    def set_values(self, strategy):
        assert isinstance(strategy, object)
        self.strategy = strategy

    def get_values(self):
        return self.strategy
