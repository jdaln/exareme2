import asyncio
import logging
import random
from datetime import datetime
from typing import Dict
from typing import List

from pydantic import BaseModel

from mipengine.controller import config as controller_config
from mipengine.controller import controller_logger as ctrl_logger
from mipengine.controller.algorithm_execution_DTOs import AlgorithmExecutionDTO
from mipengine.controller.algorithm_execution_DTOs import NodesTasksHandlersDTO
from mipengine.controller.algorithm_executor import AlgorithmExecutor
from mipengine.controller.api.algorithm_request_dto import AlgorithmRequestDTO
from mipengine.controller.api.validator import validate_algorithm_request
from mipengine.controller.cleaner import Cleaner
from mipengine.controller.node_landscape_aggregator import node_landscape_aggregator
from mipengine.controller.node_tasks_handler_celery import NodeTasksHandlerCelery


class _NodeInfoDTO(BaseModel):
    node_id: str
    queue_address: str
    db_address: str
    tasks_timeout: int

    class Config:
        allow_mutation = False


class Controller:
    def __init__(self):
        self._node_landscape_aggregator = node_landscape_aggregator
        self._controller_logger = ctrl_logger.get_background_service_logger()
        self._cleaner = Cleaner(
            node_landscape_aggregator=self._node_landscape_aggregator
        )

    def start_cleanup_loop(self):
        self._controller_logger.info("starting cleanup_loop")
        self._cleaner.keep_cleaning_up = True
        task = asyncio.create_task(self._cleaner.cleanup_loop())
        self._controller_logger.info("started clean_up loop")
        return task

    def stop_cleanup_loop(self):
        self._cleaner.keep_cleaning_up = False

    async def exec_algorithm(
        self,
        request_id: str,
        algorithm_name: str,
        algorithm_request_dto: AlgorithmRequestDTO,
    ):
        context_id = get_a_uniqueid()
        algo_execution_logger = ctrl_logger.get_request_logger(request_id=request_id)

        data_model = algorithm_request_dto.inputdata.data_model
        datasets = algorithm_request_dto.inputdata.datasets

        node_tasks_handlers = self._get_nodes_tasks_handlers(
            data_model=data_model, datasets=datasets
        )

        algo_execution_node_ids = [
            node_tasks_handlers.global_node_tasks_handler.node_id
        ]
        for local_node_task_handler in node_tasks_handlers.local_nodes_tasks_handlers:
            algo_execution_node_ids.append(local_node_task_handler.node_id)

        self._cleaner.add_contextid_for_cleanup(context_id, algo_execution_node_ids)

        datasets_per_local_node: Dict[str, List[str]] = {
            task_handler.node_id: self._node_landscape_aggregator.get_node_specific_datasets(
                task_handler.node_id, data_model, datasets
            )
            for task_handler in node_tasks_handlers.local_nodes_tasks_handlers
        }

        try:
            algorithm_result = await self._exec_algorithm_with_task_handlers(
                request_id=request_id,
                context_id=context_id,
                algorithm_name=algorithm_name,
                algorithm_request_dto=algorithm_request_dto,
                tasks_handlers=node_tasks_handlers,
                datasets_per_local_node=datasets_per_local_node,
                logger=algo_execution_logger,
            )
        finally:
            self._cleaner.release_contextid_for_cleanup(context_id=context_id)

        return algorithm_result

    def _append_context_id_for_cleanup(self, context_id: str, node_ids: List[str]):
        if context_id not in self._nodes_for_cleanup.keys():
            self._nodes_for_cleanup[context_id] = node_ids
        else:
            # getting in here would mean that an algorithm with the same context_id has
            # finished and is currently in the cleanup process, this indicates context_id
            # collision.
            self._controller_logger.warning(
                f"An algorithm with the same {context_id=} was previously executed and"
                f"it is still in the cleanup process. This should not happen..."
            )
            for node_id in node_ids:
                self._nodes_for_cleanup[context_id].append(node_id)

    async def _exec_algorithm_with_task_handlers(
        self,
        request_id: str,
        context_id: str,
        algorithm_name: str,
        algorithm_request_dto: AlgorithmRequestDTO,
        tasks_handlers: NodesTasksHandlersDTO,
        datasets_per_local_node: Dict[str, List[str]],
        logger: logging.Logger,
    ) -> str:
        algorithm_execution_dto = AlgorithmExecutionDTO(
            request_id=request_id,
            context_id=context_id,
            algorithm_name=algorithm_name,
            data_model=algorithm_request_dto.inputdata.data_model,
            datasets_per_local_node=datasets_per_local_node,
            x_vars=algorithm_request_dto.inputdata.x,
            y_vars=algorithm_request_dto.inputdata.y,
            var_filters=algorithm_request_dto.inputdata.filters,
            algo_parameters=algorithm_request_dto.parameters,
            algo_flags=algorithm_request_dto.flags,
        )
        algorithm_executor = AlgorithmExecutor(algorithm_execution_dto, tasks_handlers)

        loop = asyncio.get_running_loop()

        logger.info(f"starts executing->  {algorithm_name=}")
        # TODO: AlgorithmExecutor is not yet implemented with asyncio. This is a
        # temporary solution for not blocking the calling function
        algorithm_result = await loop.run_in_executor(None, algorithm_executor.run)
        logger.info(f"finished execution->  {algorithm_name=}")
        logger.info(f"algorithm result-> {algorithm_result.json()=}")

        return algorithm_result.json()

    def validate_algorithm_execution_request(
        self, algorithm_name: str, algorithm_request_dto: AlgorithmRequestDTO
    ):
        available_datasets_per_data_model = (
            self.get_all_available_datasets_per_data_model()
        )
        validate_algorithm_request(
            algorithm_name=algorithm_name,
            algorithm_request_dto=algorithm_request_dto,
            available_datasets_per_data_model=available_datasets_per_data_model,
        )

    def start_node_landscape_aggregator(self):
        self._controller_logger.info("starting node landscape aggregator")
        self._node_landscape_aggregator.start()
        self._controller_logger.info("started node landscape aggregator")

    def stop_node_landscape_aggregator(self):
        self._node_landscape_aggregator.stop()

    def get_datasets_location(self):
        return self._node_landscape_aggregator.datasets_location

    def get_data_models(self):
        return self._node_landscape_aggregator.get_data_models()

    def get_all_available_data_models(self):
        return list(self._node_landscape_aggregator.data_models.keys())

    def get_all_available_datasets_per_data_model(self):
        return (
            self._node_landscape_aggregator.get_all_available_datasets_per_data_model()
        )

    def get_all_local_nodes(self):
        return self._node_landscape_aggregator.get_all_local_nodes()

    def get_global_node(self):
        return self._node_landscape_aggregator.get_global_node()

    def _get_nodes_tasks_handlers(
        self, data_model: str, datasets: List[str]
    ) -> NodesTasksHandlersDTO:
        global_node = self._node_landscape_aggregator.get_global_node()
        global_node_tasks_handler = _create_node_task_handler(
            _NodeInfoDTO(
                node_id=global_node.id,
                queue_address=":".join([str(global_node.ip), str(global_node.port)]),
                db_address=":".join([str(global_node.db_ip), str(global_node.db_port)]),
                tasks_timeout=controller_config.rabbitmq.celery_tasks_timeout,
            )
        )

        # Get only the relevant nodes from the node registry
        local_nodes_info = self._get_nodes_info_by_dataset(
            data_model=data_model, datasets=datasets
        )
        local_nodes_tasks_handlers = [
            _create_node_task_handler(task_handler) for task_handler in local_nodes_info
        ]

        return NodesTasksHandlersDTO(
            global_node_tasks_handler=global_node_tasks_handler,
            local_nodes_tasks_handlers=local_nodes_tasks_handlers,
        )

    def _get_node_info_by_id(self, node_id: str) -> _NodeInfoDTO:
        node = self._node_landscape_aggregator.get_node_info(node_id)
        return _NodeInfoDTO(
            node_id=node.id,
            queue_address=":".join([str(node.ip), str(node.port)]),
            db_address=":".join([str(node.db_ip), str(node.db_port)]),
            tasks_timeout=controller_config.rabbitmq.celery_tasks_timeout,
        )

    def _get_nodes_info_by_dataset(
        self, data_model: str, datasets: List[str]
    ) -> List[_NodeInfoDTO]:
        local_node_ids = (
            self._node_landscape_aggregator.get_node_ids_with_any_of_datasets(
                data_model=data_model,
                datasets=datasets,
            )
        )
        local_nodes_info = [
            self._node_landscape_aggregator.get_node_info(node_id)
            for node_id in local_node_ids
        ]
        nodes_info = []
        for local_node in local_nodes_info:
            nodes_info.append(
                _NodeInfoDTO(
                    node_id=local_node.id,
                    queue_address=":".join([str(local_node.ip), str(local_node.port)]),
                    db_address=":".join(
                        [str(local_node.db_ip), str(local_node.db_port)]
                    ),
                    tasks_timeout=controller_config.rabbitmq.celery_tasks_timeout,
                )
            )

        return nodes_info


def _create_node_task_handler(node_info: _NodeInfoDTO) -> NodeTasksHandlerCelery:
    return NodeTasksHandlerCelery(
        node_id=node_info.node_id,
        node_queue_addr=node_info.queue_address,
        node_db_addr=node_info.db_address,
        tasks_timeout=node_info.tasks_timeout,
    )


def get_a_uniqueid() -> str:
    uid = datetime.now().microsecond + (random.randrange(1, 100 + 1) * 100000)
    return f"{uid}"
