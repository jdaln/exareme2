#!/bin/bash

#echo "Starting global"
python exareme2/algorithms/lr_imaging_mnist_global.py &
sleep 3
python exareme2/algorithms/lr_imaging_mnist_local
#done

# This will allow you to use CTRL+C to stop all background processes
#trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM
# Wait for all background processes to complete
wait
