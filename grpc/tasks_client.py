import logging
import random

import tasks_pb2
import tasks_pb2_grpc
from grpc_status import rpc_status

import grpc


def task_get_table(stub):
    print(stub.GetTable(tasks_pb2.Name(name="testname")))


def run():
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = tasks_pb2_grpc.TablesStub(channel)
        print("-------------- GetTable --------------")
        print(stub.GetTable(tasks_pb2.Name(name="testname")))
        print("-------------- GetTable ERROR --------------")
        try:
            print(stub.GetTable(tasks_pb2.Name(name="testname2")))
        except grpc.RpcError as rpc_error:
            print(rpc_error.details())


if __name__ == "__main__":
    logging.basicConfig()
    run()
