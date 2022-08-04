import threading
import time
import traceback
from abc import ABC
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from pydantic import BaseModel

from mipengine.controller import config as controller_config
from mipengine.controller import controller_logger as ctrl_logger
from mipengine.controller.celery_app import CeleryConnectionError
from mipengine.controller.celery_app import CeleryTaskTimeoutException
from mipengine.controller.federation_info_logs import log_datamodel_added
from mipengine.controller.federation_info_logs import log_datamodel_removed
from mipengine.controller.federation_info_logs import log_dataset_added
from mipengine.controller.federation_info_logs import log_dataset_removed
from mipengine.controller.federation_info_logs import log_node_joined_federation
from mipengine.controller.federation_info_logs import log_node_left_federation
from mipengine.controller.node_info_tasks_handler import NodeInfoTasksHandler
from mipengine.controller.nodes_addresses import NodesAddressesFactory
from mipengine.node_info_DTOs import NodeInfo
from mipengine.node_info_DTOs import NodeRole
from mipengine.node_tasks_DTOs import CommonDataElement
from mipengine.node_tasks_DTOs import CommonDataElements
from mipengine.singleton import Singleton

logger = ctrl_logger.get_background_service_logger()
NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID = "NODE_LANDSCAPE_AGGREGATOR"
NODE_LANDSCAPE_AGGREGATOR_UPDATE_INTERVAL = (
    controller_config.node_landscape_aggregator_update_interval
)
CELERY_TASKS_TIMEOUT = controller_config.rabbitmq.celery_tasks_timeout
NODE_INFO_TASKS_TIMEOUT = (
    controller_config.rabbitmq.celery_tasks_timeout
    + controller_config.rabbitmq.celery_run_udf_task_timeout
)


def _get_nodes_info(nodes_socket_addr: List[str]) -> List[NodeInfo]:
    node_info_tasks_handlers = [
        NodeInfoTasksHandler(
            node_queue_addr=node_socket_addr, tasks_timeout=NODE_INFO_TASKS_TIMEOUT
        )
        for node_socket_addr in nodes_socket_addr
    ]
    nodes_info = []
    for tasks_handler in node_info_tasks_handlers:
        try:
            async_result = tasks_handler.queue_node_info_task(
                request_id=NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID
            )
            result = tasks_handler.result_node_info_task(
                async_result=async_result,
                request_id=NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID,
            )
            nodes_info.append(result)
        except (CeleryConnectionError, CeleryTaskTimeoutException) as exc:
            # just log the exception do not reraise it
            logger.warning(exc)
        except Exception:
            # just log full traceback exception as error and do not reraise it
            logger.error(traceback.format_exc())
    return nodes_info


def _get_node_datasets_per_data_model(
    node_socket_addr: str,
) -> Dict[str, Dict[str, str]]:
    tasks_handler = NodeInfoTasksHandler(
        node_queue_addr=node_socket_addr, tasks_timeout=NODE_INFO_TASKS_TIMEOUT
    )
    try:
        async_result = tasks_handler.queue_node_datasets_per_data_model_task(
            request_id=NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID
        )
        datasets_per_data_model = (
            tasks_handler.result_node_datasets_per_data_model_task(
                async_result=async_result,
                request_id=NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID,
            )
        )
    except (CeleryConnectionError, CeleryTaskTimeoutException) as exc:
        # just log the exception do not reraise it
        logger.warning(exc)
        return {}
    except Exception:
        # just log full traceback exception as error and do not reraise it
        logger.error(traceback.format_exc())
        return {}
    return datasets_per_data_model


def _get_node_cdes(node_socket_addr: str, data_model: str) -> CommonDataElements:
    tasks_handler = NodeInfoTasksHandler(
        node_queue_addr=node_socket_addr, tasks_timeout=NODE_INFO_TASKS_TIMEOUT
    )
    try:
        async_result = tasks_handler.queue_data_model_cdes_task(
            request_id=NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID, data_model=data_model
        )
        node_cdes = tasks_handler.result_data_model_cdes_task(
            async_result=async_result, request_id=NODE_LANDSCAPE_AGGREGATOR_REQUEST_ID
        )
        return node_cdes
    except (CeleryConnectionError, CeleryTaskTimeoutException) as exc:
        # just log the exception do not reraise it
        logger.warning(exc)
    except Exception:
        # just log full traceback exception as error and do not reraise it
        logger.error(traceback.format_exc())


class ImmutableBaseModel(BaseModel, ABC):
    class Config:
        allow_mutation = False


def _get_node_socket_addr(node_info: NodeInfo):
    return f"{node_info.ip}:{node_info.port}"


def _have_common_elements(a: List[Any], b: List[Any]):
    return bool(set(a) & set(b))


class DataModelsCDES(ImmutableBaseModel):
    """
    A dictionary representation of the cdes of each data model.
    Key values are data models.
    Values are CommonDataElements.
    """

    data_models_cdes: Optional[Dict[str, CommonDataElements]] = {}


class DatasetsLocations(ImmutableBaseModel):
    """
    A dictionary representation of the locations of each dataset in the federation.
    Key values are data models because a dataset may be available in multiple data_models.
    Values are Dictionaries of datasets and their locations.
    """

    datasets_locations: Optional[Dict[str, Dict[str, str]]] = {}


class DataModelRegistry(ImmutableBaseModel):
    data_models: Optional[DataModelsCDES] = DataModelsCDES()
    datasets_locations: Optional[DatasetsLocations] = DatasetsLocations()

    class Config:
        allow_mutation = False
        arbitrary_types_allowed = True

    def get_cdes_specific_data_model(self, data_model) -> CommonDataElements:
        return self.data_models.data_models_cdes[data_model]

    def get_all_available_datasets_per_data_model(self) -> Dict[str, List[str]]:
        """
        Returns a dictionary with all the currently available data_models on the
        system as keys and lists of datasets as values. Without duplicates
        """
        return (
            {
                data_model: list(datasets_and_locations_of_specific_data_model.keys())
                for data_model, datasets_and_locations_of_specific_data_model in self.datasets_locations.datasets_locations.items()
            }
            if self.datasets_locations
            else {}
        )

    def data_model_exists(self, data_model: str) -> bool:
        return data_model in self.datasets_locations.datasets_locations

    def dataset_exists(self, data_model: str, dataset: str) -> bool:
        return (
            data_model in self.datasets_locations.datasets_locations
            and dataset in self.datasets_locations.datasets_locations[data_model]
        )

    def get_node_ids_with_any_of_datasets(
        self, data_model: str, datasets: List[str]
    ) -> List[str]:
        if not self.data_model_exists(data_model):
            return []

        local_nodes_with_datasets = [
            self.datasets_locations.datasets_locations[data_model][dataset]
            for dataset in self.datasets_locations.datasets_locations[data_model]
            if dataset in datasets
        ]
        return list(set(local_nodes_with_datasets))

    def get_node_specific_datasets(
        self, node_id: str, data_model: str, wanted_datasets: List[str]
    ) -> List[str]:
        """
        From the datasets provided, returns only the ones located in the node.

        Parameters
        ----------
        node_id: the id of the node
        data_model: the data model of the datasets
        wanted_datasets: the datasets to look for

        Returns
        -------
        some, all or none of bthe wanted_datasets that are located in the node
        """
        if not self.data_model_exists(data_model):
            raise ValueError(
                f"Data model '{data_model}' is not available in the node '{node_id}'."
            )

        datasets_in_node = [
            dataset
            for dataset in self.datasets_locations.datasets_locations[data_model]
            if dataset in wanted_datasets
            and node_id
            == self.datasets_locations.datasets_locations[data_model][dataset]
        ]
        return datasets_in_node


class NodeRegistry(ImmutableBaseModel):
    def __init__(self, nodes_info=None):
        if nodes_info:
            global_nodes = [
                node_info
                for node_info in nodes_info
                if node_info.role == NodeRole.GLOBALNODE
            ]
            local_nodes = [
                node_info
                for node_info in nodes_info
                if node_info.role == NodeRole.LOCALNODE
            ]
            _nodes_per_id = {
                node_info.id: node_info for node_info in global_nodes + local_nodes
            }
            super().__init__(
                global_nodes=global_nodes,
                local_nodes=local_nodes,
                nodes_per_id=_nodes_per_id,
            )
        else:
            super().__init__()

    global_nodes: List[NodeInfo] = []
    local_nodes: List[NodeInfo] = []
    nodes_per_id: Dict[str, NodeInfo] = {}

    class Config:
        allow_mutation = False
        arbitrary_types_allowed = True


class _NLARegistries(ImmutableBaseModel):
    node_registry: Optional[NodeRegistry] = NodeRegistry()
    data_model_registry: Optional[DataModelRegistry] = DataModelRegistry()

    class Config:
        allow_mutation = False
        arbitrary_types_allowed = True


class DatasetsLabels(ImmutableBaseModel):
    """
    A dictionary representation of a dataset's information.
    Key values are the names of the datasets.
    Values are the labels of the datasets.
    """

    datasets_labels: Dict[str, str]


class DatasetsLabelsPerDataModel(ImmutableBaseModel):
    """
    Key values are the names of the data_models.
    Values are DatasetsLabels.
    """

    datasets_labels_per_data_model: Dict[str, DatasetsLabels]


class DataModelsMetadata(ImmutableBaseModel):
    """
    A dictionary representation of a data models's Metadata.
    Key values are data models.
    Values are tuples that contain datasets info and cdes for a specific data model.
    """

    data_models_metadata: Dict[str, Tuple[DatasetsLabels, Optional[CommonDataElements]]]


class DataModelsMetadataPerNode(ImmutableBaseModel):
    """
    A dictionary representation of all information for the data models's Metadata per node.
    Key values are nodes.
    Values are data models's Metadata.
    """

    data_models_metadata_per_node: Dict[str, DataModelsMetadata]


class NodeLandscapeAggregator(metaclass=Singleton):
    def __init__(self):
        self._registries = _NLARegistries()
        self._keep_updating = True
        self._update_loop_thread = None

    def _update(self):
        """
        Node Landscape Aggregator(NLA) is a module that handles the aggregation of necessary information,
        to keep up-to-date and in sync the Node Registry and the Data Model Registry.
        The Node Registry contains information about the node such as id, ip, port etc.
        The Data Model Registry contains two types of information, data_models and datasets_locations.
        data_models contains information about the data models and their corresponding cdes.
        datasets_locations contains information about datasets and their locations(nodes).
        NLA periodically will send requests (get_node_info, get_node_datasets_per_data_model, get_data_model_cdes),
        to the nodes to retrieve the current information that they contain.
        Once all information about data models and cdes is aggregated,
        any data model that is incompatible across nodes will be removed.
        A data model is incompatible when the cdes across nodes are not identical, except one edge case.
        The edge case is that the cdes can only contain a difference in the field of 'enumerations' in
        the cde with code 'dataset' and still be considered compatible.
        For each data model the 'enumerations' field in the cde with code 'dataset' is updated with all datasets across nodes.
        Once all the information is aggregated and validated the NLA will provide the information to the Node Registry and to the Data Model Registry.
        """
        (
            nodes_info,
            data_models_metadata_per_node,
        ) = _fetch_nodes_metadata()
        node_registry = NodeRegistry(nodes_info=nodes_info)
        dmr = _crunch_data_model_registry_data(data_models_metadata_per_node)

        self._set_new_registries(node_registry, dmr)

        logger.debug(f"Nodes:{[node_info.id for node_info in self.get_nodes()]}")

    def _update_loop(self):
        while self._keep_updating:
            try:
                self._update()
            except Exception as exc:
                logger.warning(
                    f"NodeLandscapeAggregator caught an exception but will continue to "
                    f"update {exc=}"
                )
                tr = traceback.format_exc()
                logger.error(tr)
            finally:
                time.sleep(NODE_LANDSCAPE_AGGREGATOR_UPDATE_INTERVAL)

    def start(self):
        self.stop()
        self._keep_updating = True
        self._update_loop_thread = threading.Thread(
            target=self._update_loop, daemon=True
        )
        self._update_loop_thread.start()

    def stop(self):
        if self._update_loop_thread and self._update_loop_thread.is_alive():
            self._keep_updating = False
            self._update_loop_thread.join()

    def _set_new_registries(self, node_registry, data_model_registry):
        _log_node_changes(
            self.get_nodes(),
            list(node_registry.nodes_per_id.values()),
        )
        _log_data_model_changes(
            self._registries.data_model_registry.data_models.data_models_cdes,
            data_model_registry.data_models.data_models_cdes,
        )
        _log_dataset_changes(
            self._registries.data_model_registry.datasets_locations.datasets_locations,
            data_model_registry.datasets_locations.datasets_locations,
        )
        self._registries = _NLARegistries(
            node_registry=node_registry, data_model_registry=data_model_registry
        )

    def get_nodes(self) -> List[NodeInfo]:
        return list(self._registries.node_registry.nodes_per_id.values())

    def get_global_node(self) -> NodeInfo:
        if not self._registries.node_registry.global_nodes:
            raise Exception("Global Node is unavailable")
        return self._registries.node_registry.global_nodes[0]

    def get_all_local_nodes(self) -> List[NodeInfo]:
        return self._registries.node_registry.local_nodes

    def get_node_info(self, node_id: str) -> NodeInfo:
        return self._registries.node_registry.nodes_per_id[node_id]

    def get_cdes(self, data_model: str) -> Dict[str, CommonDataElement]:
        return self._registries.data_model_registry.get_cdes_specific_data_model(
            data_model
        ).values

    def get_cdes_per_data_model(self) -> DataModelsCDES:
        return self._registries.data_model_registry.data_models

    def get_datasets_locations(self) -> DatasetsLocations:
        return self._registries.data_model_registry.datasets_locations

    def get_all_available_datasets_per_data_model(self) -> Dict[str, List[str]]:
        return (
            self._registries.data_model_registry.get_all_available_datasets_per_data_model()
        )

    def data_model_exists(self, data_model: str) -> bool:
        return self._registries.data_model_registry.data_model_exists(data_model)

    def dataset_exists(self, data_model: str, dataset: str) -> bool:
        return self._registries.data_model_registry.dataset_exists(data_model, dataset)

    def get_node_ids_with_any_of_datasets(
        self, data_model: str, datasets: List[str]
    ) -> List[str]:
        return self._registries.data_model_registry.get_node_ids_with_any_of_datasets(
            data_model, datasets
        )

    def get_node_specific_datasets(
        self, node_id: str, data_model: str, wanted_datasets: List[str]
    ) -> List[str]:
        return self._registries.data_model_registry.get_node_specific_datasets(
            node_id, data_model, wanted_datasets
        )


def _fetch_nodes_metadata() -> Tuple[
    List[NodeInfo],
    DataModelsMetadataPerNode,
]:
    """
    Returns a list of all the nodes in the federation and their metadata (data_models, datasets, cdes).
    """
    nodes_addresses = (
        NodesAddressesFactory(
            controller_config.deployment_type, controller_config.localnodes
        )
        .get_nodes_addresses()
        .socket_addresses
    )
    logger.error(nodes_addresses)
    nodes_info = _get_nodes_info(nodes_addresses)
    local_nodes = [
        node_info for node_info in nodes_info if node_info.role == NodeRole.LOCALNODE
    ]
    data_models_metadata_per_node = _get_data_models_metadata_per_node(local_nodes)
    return nodes_info, data_models_metadata_per_node


def _crunch_data_model_registry_data(
    data_models_metadata_per_node: DataModelsMetadataPerNode,
) -> DataModelRegistry:

    incompatible_data_models = _get_incompatible_data_models(
        data_models_metadata_per_node
    )
    data_models_metadata_per_node_with_compatible_data_models = (
        _remove_incompatible_data_models_from_data_models_metadata_per_node(
            data_models_metadata_per_node, incompatible_data_models
        )
    )
    (
        datasets_locations,
        datasets_labels_per_data_model,
    ) = _aggregate_datasets_locations_and_labels(
        data_models_metadata_per_node_with_compatible_data_models
    )
    data_models_cdes = _aggregate_data_models_cdes(
        data_models_metadata_per_node_with_compatible_data_models,
        datasets_labels_per_data_model,
    )

    return DataModelRegistry(
        data_models=data_models_cdes, datasets_locations=datasets_locations
    )


def _get_data_models_metadata_per_node(
    nodes: List[NodeInfo],
) -> DataModelsMetadataPerNode:
    data_models_metadata_per_node = {}

    for node_info in nodes:
        data_models_metadata = {}

        node_socket_addr = _get_node_socket_addr(node_info)
        datasets_per_data_model = _get_node_datasets_per_data_model(node_socket_addr)
        if datasets_per_data_model:
            node_socket_addr = _get_node_socket_addr(node_info)
            for data_model, datasets in datasets_per_data_model.items():
                cdes = _get_node_cdes(node_socket_addr, data_model)
                cdes = cdes if cdes else None
                data_models_metadata[data_model] = (
                    DatasetsLabels(datasets_labels=datasets),
                    cdes,
                )
        data_models_metadata_per_node[node_info.id] = DataModelsMetadata(
            data_models_metadata=data_models_metadata
        )

    return DataModelsMetadataPerNode(
        data_models_metadata_per_node=data_models_metadata_per_node
    )


def _aggregate_datasets_locations_and_labels(
    data_models_metadata_per_node,
) -> Tuple[DatasetsLocations, DatasetsLabelsPerDataModel]:
    """
    Args:
        data_models_metadata_per_node
    Returns:
        A tuple with:
         1. DatasetsLocations
         2. DatasetsLabelsPerDataModel
    """
    datasets_locations = {}
    datasets_labels = {}
    for (
        node_id,
        data_models_metadata,
    ) in data_models_metadata_per_node.data_models_metadata_per_node.items():
        for (
            data_model,
            datasets_and_cdes,
        ) in data_models_metadata.data_models_metadata.items():
            datasets, _ = datasets_and_cdes

            current_labels = (
                datasets_labels[data_model].datasets_labels
                if data_model in datasets_labels
                else {}
            )
            current_datasets = (
                datasets_locations[data_model]
                if data_model in datasets_locations
                else {}
            )

            for dataset_name, dataset_label in datasets.datasets_labels.items():
                current_labels[dataset_name] = dataset_label

                if dataset_name in current_datasets:
                    current_datasets[dataset_name].append(node_id)
                else:
                    current_datasets[dataset_name] = [node_id]

            datasets_labels[data_model] = DatasetsLabels(datasets_labels=current_labels)
            datasets_locations[data_model] = current_datasets

    datasets_locations_without_duplicates = {}
    for data_model, dataset_locations in datasets_locations.items():
        datasets_locations_without_duplicates[data_model] = {}

        for dataset, node_ids in dataset_locations.items():
            if len(node_ids) == 1:
                datasets_locations_without_duplicates[data_model][dataset] = node_ids[0]
            else:
                del datasets_labels[data_model].datasets_labels[dataset]
                _log_duplicated_dataset(node_ids, data_model, dataset)

    return DatasetsLocations(
        datasets_locations=datasets_locations_without_duplicates
    ), DatasetsLabelsPerDataModel(datasets_labels_per_data_model=datasets_labels)


def _aggregate_data_models_cdes(
    data_models_metadata_per_node: DataModelsMetadataPerNode,
    datasets_labels_per_data_model: DatasetsLabelsPerDataModel,
) -> DataModelsCDES:
    data_models = {}
    for (
        node_id,
        data_models_metadata,
    ) in data_models_metadata_per_node.data_models_metadata_per_node.items():
        for (
            data_model,
            datasets_and_cdes,
        ) in data_models_metadata.data_models_metadata.items():
            _, cdes = datasets_and_cdes
            data_models[data_model] = cdes
            dataset_cde = cdes.values["dataset"]
            new_dataset_cde = CommonDataElement(
                code=dataset_cde.code,
                label=dataset_cde.label,
                sql_type=dataset_cde.sql_type,
                is_categorical=dataset_cde.is_categorical,
                enumerations=datasets_labels_per_data_model.datasets_labels_per_data_model[
                    data_model
                ].datasets_labels,
                min=dataset_cde.min,
                max=dataset_cde.max,
            )
            data_models[data_model].values["dataset"] = new_dataset_cde
    return DataModelsCDES(data_models_cdes=data_models)


def _get_incompatible_data_models(
    data_models_metadata_per_node: DataModelsMetadataPerNode,
) -> List[str]:
    """
    Each node has its own data models definition.
    We need to check for each data model if the definitions across all nodes is the same.
    If the data model is not the same across all nodes containing it, we log the incompatibility.
    The data models with similar definitions across all nodes are returned.
    Parameters
    ----------
        data_models_metadata_per_node: DataModelsMetadataPerNode
    Returns
    ----------
        List[str]
            The incompatible data models
    """
    validation_dictionary = {}

    incompatible_data_models = []
    for (
        node_id,
        data_models_metadata,
    ) in data_models_metadata_per_node.data_models_metadata_per_node.items():
        for (
            data_model,
            datasets_and_cdes,
        ) in data_models_metadata.data_models_metadata.items():
            _, cdes = datasets_and_cdes

            if data_model in incompatible_data_models or not cdes:
                continue

            if data_model in validation_dictionary:
                valid_node_id, valid_cdes = validation_dictionary[data_model]
                if not valid_cdes == cdes:
                    nodes = [node_id, valid_node_id]
                    incompatible_data_models.append(data_model)
                    _log_incompatible_data_models(nodes, data_model, [cdes, valid_cdes])
                    break
            else:
                validation_dictionary[data_model] = (node_id, cdes)

    return incompatible_data_models


def _remove_incompatible_data_models_from_data_models_metadata_per_node(
    data_models_metadata_per_node: DataModelsMetadataPerNode,
    incompatible_data_models: List[str],
) -> DataModelsMetadataPerNode:
    return DataModelsMetadataPerNode(
        data_models_metadata_per_node={
            node_id: DataModelsMetadata(
                data_models_metadata={
                    data_model: datasets_and_cdes
                    for data_model, datasets_and_cdes in data_models_metadata.data_models_metadata.items()
                    if data_model not in incompatible_data_models
                    and datasets_and_cdes[1]
                }
            )
            for node_id, data_models_metadata in data_models_metadata_per_node.data_models_metadata_per_node.items()
        }
    )


def _log_node_changes(old_nodes, new_nodes):
    old_nodes_per_node_id = {node.id: node for node in old_nodes}
    new_nodes_per_node_id = {node.id: node for node in new_nodes}
    added_nodes = set(new_nodes_per_node_id.keys()) - set(old_nodes_per_node_id.keys())
    for node in added_nodes:
        log_node_joined_federation(logger, node)
    removed_nodes = set(old_nodes_per_node_id.keys()) - set(
        new_nodes_per_node_id.keys()
    )
    for node in removed_nodes:
        log_node_left_federation(logger, node)


def _log_data_model_changes(old_data_models, new_data_models):
    added_data_models = new_data_models.keys() - old_data_models.keys()
    for data_model in added_data_models:
        log_datamodel_added(data_model, logger)
    removed_data_models = old_data_models.keys() - new_data_models.keys()
    for data_model in removed_data_models:
        log_datamodel_removed(data_model, logger)


def _log_dataset_changes(old_datasets_locations, new_datasets_locations):
    _log_datasets_added(old_datasets_locations, new_datasets_locations)
    _log_datasets_removed(old_datasets_locations, new_datasets_locations)


def _log_datasets_added(old_datasets_locations, new_datasets_locations):
    for data_model in new_datasets_locations:
        added_datasets = new_datasets_locations[data_model].keys()
        if data_model in old_datasets_locations:
            added_datasets -= old_datasets_locations[data_model].keys()
        for dataset in added_datasets:
            log_dataset_added(
                data_model,
                dataset,
                logger,
                new_datasets_locations[data_model][dataset],
            )


def _log_datasets_removed(old_datasets_locations, new_datasets_locations):
    for data_model in old_datasets_locations:
        removed_datasets = old_datasets_locations[data_model].keys()
        if data_model in new_datasets_locations:
            removed_datasets -= new_datasets_locations[data_model].keys()
        for dataset in removed_datasets:
            log_dataset_removed(
                data_model,
                dataset,
                logger,
                old_datasets_locations[data_model][dataset],
            )


def _log_incompatible_data_models(nodes, data_model, conflicting_cdes):
    logger.info(
        f"""Nodes: '[{", ".join(nodes)}]' on data model '{data_model}' have incompatibility on the following cdes: '[{", ".join([cdes.__str__() for cdes in conflicting_cdes])}]' """
    )


def _log_duplicated_dataset(nodes, data_model, dataset):
    logger.info(
        f"""Dataset '{dataset}' of the data_model: '{data_model}' is not unique in the federation. Nodes that contain the dataset: '[{", ".join(nodes)}]'"""
    )
