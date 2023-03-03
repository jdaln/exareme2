#!/usr/bin/env bash
while true
do
  echo 'Testing'
  pytest tests/algorithm_validation_tests/test_linearregression_cv_validation.py -n 16 | tail -n 1 >> results.txt
done