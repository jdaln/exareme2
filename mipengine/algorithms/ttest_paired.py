import json

import numpy
from pydantic import BaseModel

from mipengine.udfgen import secure_transfer
from mipengine.udfgen.udfgenerator import literal
from mipengine.udfgen.udfgenerator import relation
from mipengine.udfgen.udfgenerator import transfer
from mipengine.udfgen.udfgenerator import udf


class TtestResult(BaseModel):
    t_stat: float
    df: int
    p: float
    mean_diff: float
    se_diff: float
    ci_upper: float
    ci_lower: float
    cohens_d: float


def run(algo_interface):
    local_run = algo_interface.run_udf_on_local_nodes
    global_run = algo_interface.run_udf_on_global_node
    alpha = algo_interface.algorithm_parameters["alpha"]
    alternative = algo_interface.algorithm_parameters["alt_hypothesis"]

    X_relation, Y_relation = algo_interface.create_primary_data_views(
        variable_groups=[algo_interface.x_variables, algo_interface.y_variables],
    )

    sec_local_transfer = local_run(
        func=local_paired,
        keyword_args=dict(y=Y_relation, x=X_relation),
        share_to_global=[True],
    )

    result = global_run(
        func=global_paired,
        keyword_args=dict(
            sec_local_transfer=sec_local_transfer, alpha=alpha, alternative=alternative
        ),
    )

    result = json.loads(result.get_table_data()[0][0])
    res = TtestResult(
        t_stat=result["t_stat"],
        df=result["df"],
        p=result["p"],
        mean_diff=result["mean_diff"],
        se_diff=result["se_diff"],
        ci_upper=result["ci_upper"],
        ci_lower=result["ci_lower"],
        cohens_d=result["cohens_d"],
    )

    return res


@udf(
    y=relation(),
    x=relation(),
    return_type=[secure_transfer(sum_op=True)],
)
def local_paired(x, y):
    x1 = x.reset_index(drop=True).to_numpy().squeeze()
    x2 = y.reset_index(drop=True).to_numpy().squeeze()
    x1_sum = sum(x1)
    x2_sum = sum(x2)
    n_obs = len(x)
    diff = sum(x1 - x2)
    diff_sqrd = sum((x1 - x2) ** 2)
    x1_sqrd_sum = sum(x1**2)
    x2_sqrd_sum = sum(x2**2)

    sec_transfer_ = {
        "n_obs": {"data": n_obs, "operation": "sum", "type": "int"},
        "sum_x1": {"data": x1_sum.item(), "operation": "sum", "type": "float"},
        "sum_x2": {"data": x2_sum.item(), "operation": "sum", "type": "float"},
        "diff": {"data": diff.tolist(), "operation": "sum", "type": "float"},
        "diff_sqrd": {"data": diff_sqrd.tolist(), "operation": "sum", "type": "float"},
        "x1_sqrd_sum": {
            "data": x1_sqrd_sum.tolist(),
            "operation": "sum",
            "type": "float",
        },
        "x2_sqrd_sum": {
            "data": x2_sqrd_sum.tolist(),
            "operation": "sum",
            "type": "float",
        },
    }

    return sec_transfer_


@udf(
    sec_local_transfer=secure_transfer(sum_op=True),
    alpha=literal(),
    alternative=literal(),
    return_type=[transfer()],
)
def global_paired(sec_local_transfer, alpha, alternative):
    from scipy.stats import t

    n_obs = sec_local_transfer["n_obs"]
    sum_x1 = sec_local_transfer["sum_x1"]
    sum_x2 = sec_local_transfer["sum_x2"]
    diff_sum = sec_local_transfer["diff"]
    diff_sqrd_sum = sec_local_transfer["diff_sqrd"]
    x1_sqrd_sum = sec_local_transfer["x1_sqrd_sum"]
    x2_sqrd_sum = sec_local_transfer["x2_sqrd_sum"]

    mean_x1 = sum_x1 / n_obs
    mean_x2 = sum_x2 / n_obs
    devel_x1 = x1_sqrd_sum - 2 * mean_x1 * sum_x1 + (mean_x1**2) * n_obs
    devel_x2 = x2_sqrd_sum - 2 * sum_x2 * mean_x2 + (mean_x2**2) * n_obs
    sd_x1 = numpy.sqrt(devel_x1 / (n_obs - 1))
    sd_x2 = numpy.sqrt(devel_x2 / (n_obs - 1))

    # standard deviation of the difference between means
    sd = numpy.sqrt((diff_sqrd_sum - (diff_sum**2 / n_obs)) / (n_obs - 1))

    # standard error of the difference between means
    sed = sd / numpy.sqrt(n_obs)

    # t-statistic
    t_stat = (mean_x1 - mean_x2) / sed
    df = n_obs - 1

    # Sample mean
    sample_mean = diff_sum / n_obs

    # Confidence intervals !WARNING: The ci values are  not tested. The code should not be modified, unless there is
    # a test for the new method.
    ci_lower, ci_upper = t.interval(
        alpha=1 - alpha, df=n_obs - 1, loc=sample_mean, scale=sed
    )

    # p-value for alternative = 'greater'
    if alternative == "greater":
        p = 1.0 - t.cdf(t_stat, df)
        ci_upper = "Infinity"
    # p-value for alternative = 'less'
    elif alternative == "less":
        p = 1.0 - t.cdf(-t_stat, df)
        ci_lower = "-Infinity"
    # p-value for alternative = 'two-sided'
    else:
        p = (1.0 - t.cdf(abs(t_stat), df)) * 2.0

    # Cohen’s d
    cohens_d = (mean_x1 - mean_x2) / numpy.sqrt((sd_x1**2 + sd_x2**2) / 2)

    transfer_ = {
        "t_stat": t_stat,
        "df": df,
        "p": p,
        "mean_diff": diff_sum / n_obs,
        "se_diff": sed,
        "ci_upper": ci_upper,
        "ci_lower": ci_lower,
        "cohens_d": cohens_d,
    }

    return transfer_
