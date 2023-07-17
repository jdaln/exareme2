import logging
from concurrent import futures

import tasks_pb2
import tasks_pb2_grpc
from google.rpc import code_pb2
from google.rpc import status_pb2
from grpc_status import rpc_status

import grpc


class TablesServicer(tasks_pb2_grpc.TablesServicer):
    def GetTable(self, request, context):
        try:
            if request.name == "testname":
                return tasks_pb2.Table(name="testname", value=5)
            else:
                raise ValueError("Table not found.")
        except ValueError as exc:
            context.abort(grpc.StatusCode.UNKNOWN, f"{type(exc).__name__}: {str(exc)}")


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    tasks_pb2_grpc.add_TablesServicer_to_server(TablesServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    serve()
