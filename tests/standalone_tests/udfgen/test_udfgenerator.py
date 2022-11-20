# type: ignore
import json
import pickle
from string import Template
from typing import TypeVar

import pytest

from mipengine.datatypes import DType
from mipengine.node_tasks_DTOs import ColumnInfo
from mipengine.node_tasks_DTOs import SMPCTablesInfo
from mipengine.node_tasks_DTOs import TableInfo
from mipengine.node_tasks_DTOs import TableSchema
from mipengine.node_tasks_DTOs import TableType
from mipengine.udfgen import secure_transfer
from mipengine.udfgen.decorator import udf
from mipengine.udfgen.iotypes import DEFERRED
from mipengine.udfgen.iotypes import LiteralArg
from mipengine.udfgen.iotypes import MergeTensorType
from mipengine.udfgen.iotypes import RelationArg
from mipengine.udfgen.iotypes import StateArg
from mipengine.udfgen.iotypes import TensorArg
from mipengine.udfgen.iotypes import TransferArg
from mipengine.udfgen.iotypes import literal
from mipengine.udfgen.iotypes import merge_transfer
from mipengine.udfgen.iotypes import placeholder
from mipengine.udfgen.iotypes import relation
from mipengine.udfgen.iotypes import state
from mipengine.udfgen.iotypes import tensor
from mipengine.udfgen.iotypes import transfer
from mipengine.udfgen.iotypes import udf_logger
from mipengine.udfgen.udfgen_DTOs import UDFGenSMPCResult
from mipengine.udfgen.udfgen_DTOs import UDFGenTableResult
from mipengine.udfgen.udfgenerator import UDFBadCall
from mipengine.udfgen.udfgenerator import convert_udfgenargs_to_udfargs
from mipengine.udfgen.udfgenerator import copy_types_from_udfargs
from mipengine.udfgen.udfgenerator import generate_udf_queries
from mipengine.udfgen.udfgenerator import (
    get_create_dummy_encoded_design_matrix_execution_queries,
)
from mipengine.udfgen.udfgenerator import get_udf_templates_using_udfregistry
from mipengine.udfgen.udfgenerator import map_unknown_to_known_typeparams
from mipengine.udfgen.udfgenerator import verify_declared_typeparams_match_passed_type


def test_copy_types_from_udfargs():
    udfgen_args = {
        "a": RelationArg(table_name="A", schema=[("a", int)]),
        "b": TensorArg(table_name="B", dtype=int, ndims=2),
    }
    udfparams = copy_types_from_udfargs(udfgen_args)
    assert udfparams == {
        "a": relation(schema=[("a", int)]),
        "b": tensor(dtype=int, ndims=2),
    }


class TestVerifyTypeParams:
    @pytest.fixture(scope="class")
    def passed_type(self):
        class MockPassedType:
            a = 1
            b = 2
            c = 3

        return MockPassedType

    def test_verify_known_params_match_udfarg(self, passed_type):
        known_params = {"a": 1, "b": 2}
        assert (
            verify_declared_typeparams_match_passed_type(known_params, passed_type)
            is None
        )

    def test_verify_known_params_match_udfarg_missmatch_error(self, passed_type):
        known_params = {"a": 10, "b": 2}
        with pytest.raises(UDFBadCall):
            verify_declared_typeparams_match_passed_type(known_params, passed_type)

    def test_verify_known_params_match_udfarg_noattr_error(self, passed_type):
        known_params = {"A": 1, "b": 2}
        with pytest.raises(UDFBadCall):
            verify_declared_typeparams_match_passed_type(known_params, passed_type)


class TestTypeParamInference:
    def test_map_unknown_to_known_typeparams(self):
        unknown_params = {"a": 101, "b": 202}
        known_params = {"a": 1, "b": 2}
        inferred_typeparams = map_unknown_to_known_typeparams(
            unknown_params,
            known_params,
        )
        assert inferred_typeparams == {101: 1, 202: 2}

    def test_map_unknown_to_known_typeparams_error(self):
        unknown_params = {"d": 404, "b": 202}
        known_params = {"a": 1, "b": 2}
        with pytest.raises(ValueError):
            map_unknown_to_known_typeparams(
                unknown_params,
                known_params,
            )


def test_convert_udfgenargs_to_udfargs_relation():
    udfgen_posargs = [
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="c1", dtype=DType.INT),
                    ColumnInfo(name="c2", dtype=DType.FLOAT),
                    ColumnInfo(name="c3", dtype=DType.STR),
                ]
            ),
            type_=TableType.NORMAL,
        )
    ]
    expected_udf_posargs = [
        RelationArg(table_name="tab", schema=[("c1", int), ("c2", float), ("c3", str)])
    ]
    result, _ = convert_udfgenargs_to_udfargs(udfgen_posargs, {})
    assert result == expected_udf_posargs


def test_convert_udfgenargs_to_udfargs_tensor():
    udfgen_posargs = [
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="dim0", dtype=DType.INT),
                    ColumnInfo(name="dim1", dtype=DType.INT),
                    ColumnInfo(name="val", dtype=DType.FLOAT),
                ]
            ),
            type_=TableType.NORMAL,
        )
    ]
    expected_udf_posargs = [TensorArg(table_name="tab", dtype=float, ndims=2)]
    result, _ = convert_udfgenargs_to_udfargs(udfgen_posargs, {})
    assert result == expected_udf_posargs


def test_convert_udfgenargs_to_udfargs_literal():
    udfgen_posargs = [42]
    expected_udf_posargs = [LiteralArg(value=42)]
    result, _ = convert_udfgenargs_to_udfargs(udfgen_posargs, {})
    assert result == expected_udf_posargs


def test_convert_udfgenargs_to_udfargs_multiple_types():
    udfgen_posargs = [
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="c1", dtype=DType.INT),
                    ColumnInfo(name="c2", dtype=DType.FLOAT),
                    ColumnInfo(name="c3", dtype=DType.STR),
                ]
            ),
            type_=TableType.NORMAL,
        ),
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="dim0", dtype=DType.INT),
                    ColumnInfo(name="dim1", dtype=DType.INT),
                    ColumnInfo(name="val", dtype=DType.FLOAT),
                ]
            ),
            type_=TableType.NORMAL,
        ),
        42,
    ]
    expected_udf_posargs = [
        RelationArg(table_name="tab", schema=[("c1", int), ("c2", float), ("c3", str)]),
        TensorArg(table_name="tab", dtype=float, ndims=2),
        LiteralArg(value=42),
    ]
    result, _ = convert_udfgenargs_to_udfargs(udfgen_posargs, {})
    assert result == expected_udf_posargs


def test_convert_udfgenargs_to_transfer_udfargs():
    udfgen_posargs = [
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="transfer", dtype=DType.JSON),
                ]
            ),
            type_=TableType.REMOTE,
        ),
    ]
    expected_udf_posargs = [TransferArg(table_name="tab")]
    result, _ = convert_udfgenargs_to_udfargs(udfgen_posargs, {})
    assert result == expected_udf_posargs


def test_convert_udfgenargs_to_state_udfargs():
    udfgen_posargs = [
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="state", dtype=DType.BINARY),
                ]
            ),
            type_=TableType.NORMAL,
        ),
    ]
    expected_udf_posargs = [StateArg(table_name="tab")]
    result, _ = convert_udfgenargs_to_udfargs(udfgen_posargs, {})
    assert result == expected_udf_posargs


def test_convert_udfgenargs_to_state_udfargs_not_local():
    udfgen_posargs = [
        TableInfo(
            name="tab",
            schema_=TableSchema(
                columns=[
                    ColumnInfo(name="state", dtype=DType.BINARY),
                ]
            ),
            type_=TableType.REMOTE,
        ),
    ]

    with pytest.raises(UDFBadCall):
        convert_udfgenargs_to_udfargs(udfgen_posargs, {})


class TestUDFGenBase:
    @pytest.fixture(scope="class")
    def funcname(self, udfregistry):
        assert len(udfregistry) == 1
        return next(iter(udfregistry.keys()))

    @staticmethod
    def _get_udf_output_tablename_template_mapping(expected_udf_outputs):
        template_mapping = {}
        for udf_output in expected_udf_outputs:
            if isinstance(udf_output, UDFGenTableResult):
                tablename_placeholder = udf_output.tablename_placeholder
                template_mapping[tablename_placeholder] = tablename_placeholder
            elif isinstance(udf_output, UDFGenSMPCResult):
                tablename_placeholder = udf_output.template.tablename_placeholder
                template_mapping[tablename_placeholder] = tablename_placeholder
                if udf_output.sum_op_values:
                    tablename_placeholder = (
                        udf_output.sum_op_values.tablename_placeholder
                    )
                    template_mapping[tablename_placeholder] = tablename_placeholder
                if udf_output.min_op_values:
                    tablename_placeholder = (
                        udf_output.min_op_values.tablename_placeholder
                    )
                    template_mapping[tablename_placeholder] = tablename_placeholder
                if udf_output.max_op_values:
                    tablename_placeholder = (
                        udf_output.max_op_values.tablename_placeholder
                    )
                    template_mapping[tablename_placeholder] = tablename_placeholder
            else:
                pytest.fail(
                    "A udf_output must be of the format TableUDFOutput or SMPCUDFOutput"
                )
        return template_mapping

    @pytest.fixture(scope="class")
    def concrete_udf_def(self, expected_udfdef, expected_udf_outputs):
        """
        Replaces the udf_name placeholders in the Template.
        If the udf has loopback tables, it also replaces their names' placeholders.
        """
        template_mapping = {"udf_name": "udf_test", "request_id": "request_id_test"}
        template_mapping.update(
            self._get_udf_output_tablename_template_mapping(expected_udf_outputs)
        )
        return Template(expected_udfdef).substitute(**template_mapping)

    @pytest.fixture(scope="class")
    def concrete_udf_sel(self, expected_udf_outputs, expected_udfsel):
        """
        The udf definition could contain more than one tablename placeholders.
        The expected_udf_outputs are used to replace all the necessary fields.
        Just like in the `concrete_udf_outputs` it replaces the tablename_placeholder
        in the Templates using the same tablename.
        """
        template_mapping = {
            "udf_name": "udf_test",
        }
        template_mapping.update(
            self._get_udf_output_tablename_template_mapping(expected_udf_outputs)
        )
        return Template(expected_udfsel).substitute(**template_mapping)

    @staticmethod
    def _concrete_table_udf_outputs(output: UDFGenTableResult):
        queries = []
        template_mapping = {output.tablename_placeholder: output.tablename_placeholder}
        queries.append(output.drop_query.substitute(**template_mapping))
        queries.append(output.create_query.substitute(**template_mapping))
        return queries

    @pytest.fixture(scope="class")
    def concrete_udf_outputs(self, expected_udf_outputs):
        """
        Replaces the tablename_placeholder in the UDFOutput(s) using the same tablename.
        """
        queries = []
        for udf_output in expected_udf_outputs:
            if isinstance(udf_output, UDFGenTableResult):
                queries.extend(self._concrete_table_udf_outputs(udf_output))
            elif isinstance(udf_output, UDFGenSMPCResult):
                queries.extend(self._concrete_table_udf_outputs(udf_output.template))
                if udf_output.sum_op_values:
                    queries.extend(
                        self._concrete_table_udf_outputs(udf_output.sum_op_values)
                    )
                if udf_output.min_op_values:
                    queries.extend(
                        self._concrete_table_udf_outputs(udf_output.min_op_values)
                    )
                if udf_output.max_op_values:
                    queries.extend(
                        self._concrete_table_udf_outputs(udf_output.max_op_values)
                    )
            else:
                pytest.fail(
                    "A udf_output must be of the format TableUDFOutput or SMPCUDFOutput"
                )

        return "\n".join(queries)

    @pytest.fixture(scope="function")
    def create_transfer_table(self, globalnode_db_cursor):
        globalnode_db_cursor.execute("CREATE TABLE test_transfer_table(transfer CLOB)")
        globalnode_db_cursor.execute(
            "INSERT INTO test_transfer_table(transfer) VALUES('{\"num\":5}')"
        )

    @pytest.fixture(scope="function")
    def create_state_table(self, globalnode_db_cursor):
        state = pickle.dumps({"num": 5}).hex()
        globalnode_db_cursor.execute("CREATE TABLE test_state_table(state BLOB)")
        insert_state = f"INSERT INTO test_state_table(state) VALUES('{state}')"
        globalnode_db_cursor.execute(insert_state)

    @pytest.fixture(scope="function")
    def create_merge_transfer_table(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE test_merge_transfer_table(transfer CLOB)"
        )
        globalnode_db_cursor.execute(
            """INSERT INTO test_merge_transfer_table
                 (transfer)
               VALUES
                 ('{\"num\":5}'),
                 ('{\"num\":10}')"""
        )

    @pytest.fixture(scope="function")
    def create_secure_transfer_table(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE test_secure_transfer_table(secure_transfer CLOB)"
        )
        globalnode_db_cursor.execute(
            """INSERT INTO test_secure_transfer_table
                 (secure_transfer)
               VALUES
                 (\'{"sum": {"data": 1, "operation": "sum", "type": "int"}}\'),
                 (\'{"sum": {"data": 10, "operation": "sum", "type": "int"}}\'),
                 (\'{"sum": {"data": 100, "operation": "sum", "type": "int"}}\')"""
        )

    @pytest.fixture(scope="function")
    def create_smpc_template_table_with_sum(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE test_smpc_template_table(secure_transfer CLOB)"
        )
        globalnode_db_cursor.execute(
            'INSERT INTO test_smpc_template_table(secure_transfer) VALUES(\'{"sum": {"data": [0,1,2], "operation": "sum", "type": "int"}}\')'
        )

    @pytest.fixture(scope="function")
    def create_smpc_sum_op_values_table(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE test_smpc_sum_op_values_table(secure_transfer CLOB)"
        )
        globalnode_db_cursor.execute(
            "INSERT INTO test_smpc_sum_op_values_table(secure_transfer) VALUES('[100,200,300]')"
        )

    @pytest.fixture(scope="function")
    def create_smpc_template_table_with_sum_and_max(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE test_smpc_template_table(secure_transfer CLOB)"
        )
        globalnode_db_cursor.execute(
            'INSERT INTO test_smpc_template_table(secure_transfer) VALUES(\'{"sum": {"data": [0,1,2], "operation": "sum", "type": "int"}, '
            '"max": {"data": 0, "operation": "max", "type": "int"}}\')'
        )

    @pytest.fixture(scope="function")
    def create_smpc_max_op_values_table(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE test_smpc_max_op_values_table(secure_transfer CLOB)"
        )
        globalnode_db_cursor.execute(
            "INSERT INTO test_smpc_max_op_values_table(secure_transfer) VALUES('[58]')"
        )

    # TODO Should become more dynamic in the future.
    # It should receive a TableInfo object as input and maybe data as well.
    @pytest.fixture(scope="function")
    def create_tensor_table(self, globalnode_db_cursor):
        globalnode_db_cursor.execute(
            "CREATE TABLE tensor_in_db(dim0 INT, dim1 INT, val INT)"
        )
        globalnode_db_cursor.execute(
            """INSERT INTO tensor_in_db
                 (dim0, dim1, val)
               VALUES
                 (0, 0, 3),
                 (0, 1, 4),
                 (0, 2, 7)"""
        )


class TestUDFGen_InvalidUDFArgs_NamesMismatch(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=1),
            y=tensor(dtype=int, ndims=1),
            z=literal(),
            return_type=relation([("result", int)]),
        )
        def f(x, y, z):
            return x

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [TensorArg("table_name", dtype=int, ndims=1)]
        keywordargs = {"z": LiteralArg(1)}
        with pytest.raises(UDFBadCall) as exc:
            get_udf_templates_using_udfregistry(
                funcname=funcname,
                posargs=posargs,
                keywordargs=keywordargs,
                udfregistry=udfregistry,
                smpc_used=False,
            )
        assert "UDF argument names do not match UDF parameter names" in str(exc)


class TestUDFGen_LoggerArgument_provided_in_pos_args(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=1),
            logger=udf_logger(),
            return_type=relation([("result", int)]),
        )
        def f(x, logger):
            return x

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [TensorArg("table_name", dtype=int, ndims=1), LiteralArg(1)]
        with pytest.raises(UDFBadCall) as exc:
            get_udf_templates_using_udfregistry(
                funcname=funcname,
                posargs=posargs,
                keywordargs={},
                udfregistry=udfregistry,
                smpc_used=False,
            )
        assert "No argument should be provided for 'UDFLoggerType' parameter" in str(
            exc
        )


class TestUDFGen_LoggerArgument_provided_in_kw_args(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=1),
            logger=udf_logger(),
            return_type=relation([("result", int)]),
        )
        def f(x, logger):
            return x

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [TensorArg("table_name", dtype=int, ndims=1)]
        keywordargs = {"logger": LiteralArg(1)}
        with pytest.raises(UDFBadCall) as exc:
            get_udf_templates_using_udfregistry(
                funcname=funcname,
                posargs=posargs,
                keywordargs=keywordargs,
                udfregistry=udfregistry,
                smpc_used=False,
            )
        assert "No argument should be provided for 'UDFLoggerType' parameter" in str(
            exc
        )


class TestUDFGen_InvalidUDFArgs_TransferTableInStateArgument(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfers=state(),
            state=state(),
            return_type=transfer(),
        )
        def f(transfers, state):
            result = {"num": sum}
            return result

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [
            TableInfo(
                name="test_table_3",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
            TableInfo(
                name="test_table_5",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]
        with pytest.raises(UDFBadCall) as exc:
            generate_udf_queries(
                func_name=funcname,
                positional_args=posargs,
                keyword_args={},
                smpc_used=False,
            )
        assert "should be of type" in str(exc)


class TestUDFGen_InvalidUDFArgs_TensorTableInTransferArgument(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfers=transfer(),
            state=state(),
            return_type=transfer(),
        )
        def f(transfers, state):
            result = {"num": sum}
            return result

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [
            TableInfo(
                name="tensor_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="test_table_5",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]
        with pytest.raises(UDFBadCall) as exc:
            _ = generate_udf_queries(
                func_name=funcname,
                positional_args=posargs,
                keyword_args={},
                smpc_used=True,
            )
        assert "should be of type" in str(exc)


class TestUDFGen_Invalid_SMPCUDFInput_To_Transfer_Type(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfer=transfer(),
            return_type=transfer(),
        )
        def f(transfer):
            result = {"num": sum}
            return result

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [
            SMPCTablesInfo(
                template=TableInfo(
                    name="test_smpc_template_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
                sum_op=TableInfo(
                    name="test_smpc_sum_op_values_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
            )
        ]
        with pytest.raises(UDFBadCall) as exc:
            generate_udf_queries(
                func_name=funcname,
                positional_args=posargs,
                keyword_args={},
                smpc_used=True,
            )
        assert "should be of type" in str(exc)


class TestUDFGen_Invalid_TableInfoArgs_To_SecureTransferType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfer=secure_transfer(sum_op=True),
            return_type=transfer(),
        )
        def f(transfer):
            result = {"num": sum}
            return result

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [
            TableInfo(
                name="test_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

        with pytest.raises(UDFBadCall) as exc:
            generate_udf_queries(
                func_name=funcname,
                positional_args=posargs,
                keyword_args={},
                smpc_used=True,
            )
        assert "When smpc is used SecureTransferArg should not be" in str(exc)


class TestUDFGen_Invalid_SMPCUDFInput_with_SMPC_off(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfer=secure_transfer(sum_op=True),
            return_type=transfer(),
        )
        def f(transfer):
            result = {"num": sum}
            return result

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [
            SMPCTablesInfo(
                template=TableInfo(
                    name="test_smpc_template_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
                sum_op_values=TableInfo(
                    name="test_smpc_sum_op_values_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
            )
        ]
        with pytest.raises(UDFBadCall) as exc:
            generate_udf_queries(
                func_name=funcname,
                positional_args=posargs,
                keyword_args={},
                smpc_used=False,
            )
        assert "SMPC is not used, " in str(exc)


class TestUDFGen_InvalidUDFArgs_InconsistentTypeVars(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        T = TypeVar("T")

        @udf(
            x=tensor(dtype=T, ndims=1),
            y=tensor(dtype=T, ndims=1),
            return_type=tensor(dtype=T, ndims=1),
        )
        def f(x, y):
            return x

        return udf.registry

    def test_get_udf_templates(self, udfregistry, funcname):
        posargs = [
            TensorArg("table_name1", dtype=int, ndims=1),
            TensorArg("table_name1", dtype=float, ndims=1),
        ]
        keywordargs = {}
        with pytest.raises(ValueError) as e:
            get_udf_templates_using_udfregistry(
                funcname=funcname,
                posargs=posargs,
                keywordargs=keywordargs,
                udfregistry=udfregistry,
                smpc_used=False,
            )
        err_msg, *_ = e.value.args
        assert "inconsistent mappings" in err_msg


class TestUDFGen_TensorToTensor(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        T = TypeVar("T")

        @udf(x=tensor(dtype=T, ndims=2), return_type=tensor(dtype=DType.FLOAT, ndims=2))
        def f(x):
            result = x
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tensor_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_dim1" INT,"x_val" INT)
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'dim1', 'val'], ['x_dim0', 'x_dim1', 'x_val'])})
    result = x
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tensor_in_db."dim0",
            tensor_in_db."dim1",
            tensor_in_db."val"
        FROM
            tensor_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TensorParameterWithCapitalLetter(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        T = TypeVar("T")

        @udf(X=tensor(dtype=T, ndims=2), return_type=tensor(dtype=DType.FLOAT, ndims=2))
        def f(X):
            result = X
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tensor_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("X_dim0" INT,"X_dim1" INT,"X_val" INT)
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    X = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'dim1', 'val'], ['X_dim0', 'X_dim1', 'X_val'])})
    result = X
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tensor_in_db."dim0",
            tensor_in_db."dim1",
            tensor_in_db."val"
        FROM
            tensor_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database", "create_tensor_table")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
        create_tensor_table,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        output_table_values = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchall()
        assert output_table_values == [
            (0, 0, 3.0),
            (0, 1, 4.0),
            (0, 2, 7.0),
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_RelationToTensor(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        S = TypeVar("S")

        @udf(r=relation(schema=S), return_type=tensor(dtype=DType.FLOAT, ndims=2))
        def f(r):
            result = r
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="rel_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col0", dtype=DType.INT),
                        ColumnInfo(name="col1", dtype=DType.FLOAT),
                        ColumnInfo(name="col2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("r_row_id" INT,"r_col0" INT,"r_col1" DOUBLE,"r_col2" VARCHAR(500))
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    r = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col0', 'col1', 'col2'], ['r_row_id', 'r_col0', 'r_col1', 'r_col2'])}, 'row_id')
    result = r
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            rel_in_db."row_id",
            rel_in_db."col0",
            rel_in_db."col1",
            rel_in_db."col2"
        FROM
            rel_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_2RelationsToTensor(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        S = TypeVar("S")

        @udf(
            r1=relation(schema=S),
            r2=relation(schema=S),
            return_type=tensor(dtype=DType.FLOAT, ndims=2),
        )
        def f(r1, r2):
            result = r1
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="rel1_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col0", dtype=DType.INT),
                        ColumnInfo(name="col1", dtype=DType.FLOAT),
                        ColumnInfo(name="col2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="rel2_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col4", dtype=DType.INT),
                        ColumnInfo(name="col5", dtype=DType.FLOAT),
                        ColumnInfo(name="col6", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("r1_row_id" INT,"r1_col0" INT,"r1_col1" DOUBLE,"r1_col2" VARCHAR(500),"r2_row_id" INT,"r2_col4" INT,"r2_col5" DOUBLE,"r2_col6" VARCHAR(500))
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    r1 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col0', 'col1', 'col2'], ['r1_row_id', 'r1_col0', 'r1_col1', 'r1_col2'])}, 'row_id')
    r2 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col4', 'col5', 'col6'], ['r2_row_id', 'r2_col4', 'r2_col5', 'r2_col6'])}, 'row_id')
    result = r1
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            rel1_in_db."row_id",
            rel1_in_db."col0",
            rel1_in_db."col1",
            rel1_in_db."col2",
            rel2_in_db."row_id",
            rel2_in_db."col4",
            rel2_in_db."col5",
            rel2_in_db."col6"
        FROM
            rel1_in_db,
            rel2_in_db
        WHERE
            rel1_in_db."row_id"=rel2_in_db."row_id"
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_3RelationsToTensor(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        S = TypeVar("S")

        @udf(
            r1=relation(schema=S),
            r2=relation(schema=S),
            r3=relation(schema=S),
            return_type=tensor(dtype=DType.FLOAT, ndims=2),
        )
        def f(r1, r2, r3):
            result = r1
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="rel1_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col0", dtype=DType.INT),
                        ColumnInfo(name="col1", dtype=DType.FLOAT),
                        ColumnInfo(name="col2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="rel2_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col4", dtype=DType.INT),
                        ColumnInfo(name="col5", dtype=DType.FLOAT),
                        ColumnInfo(name="col6", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="rel3_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col8", dtype=DType.INT),
                        ColumnInfo(name="col9", dtype=DType.FLOAT),
                        ColumnInfo(name="col10", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("r1_row_id" INT,"r1_col0" INT,"r1_col1" DOUBLE,"r1_col2" VARCHAR(500),"r2_row_id" INT,"r2_col4" INT,"r2_col5" DOUBLE,"r2_col6" VARCHAR(500),"r3_row_id" INT,"r3_col8" INT,"r3_col9" DOUBLE,"r3_col10" VARCHAR(500))
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    r1 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col0', 'col1', 'col2'], ['r1_row_id', 'r1_col0', 'r1_col1', 'r1_col2'])}, 'row_id')
    r2 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col4', 'col5', 'col6'], ['r2_row_id', 'r2_col4', 'r2_col5', 'r2_col6'])}, 'row_id')
    r3 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col8', 'col9', 'col10'], ['r3_row_id', 'r3_col8', 'r3_col9', 'r3_col10'])}, 'row_id')
    result = r1
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            rel1_in_db."row_id",
            rel1_in_db."col0",
            rel1_in_db."col1",
            rel1_in_db."col2",
            rel2_in_db."row_id",
            rel2_in_db."col4",
            rel2_in_db."col5",
            rel2_in_db."col6",
            rel3_in_db."row_id",
            rel3_in_db."col8",
            rel3_in_db."col9",
            rel3_in_db."col10"
        FROM
            rel1_in_db,
            rel2_in_db,
            rel3_in_db
        WHERE
            rel1_in_db."row_id"=rel2_in_db."row_id" AND
            rel1_in_db."row_id"=rel3_in_db."row_id"
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_2SameRelationsToTensor(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        S = TypeVar("S")

        @udf(
            r1=relation(schema=S),
            r2=relation(schema=S),
            return_type=tensor(dtype=DType.FLOAT, ndims=2),
        )
        def f(r1, r2):
            result = r1
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="rel1_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col0", dtype=DType.INT),
                        ColumnInfo(name="col1", dtype=DType.FLOAT),
                        ColumnInfo(name="col2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="rel1_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="col0", dtype=DType.INT),
                        ColumnInfo(name="col1", dtype=DType.FLOAT),
                        ColumnInfo(name="col2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("r1_row_id" INT,"r1_col0" INT,"r1_col1" DOUBLE,"r1_col2" VARCHAR(500),"r2_row_id" INT,"r2_col0" INT,"r2_col1" DOUBLE,"r2_col2" VARCHAR(500))
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    r1 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col0', 'col1', 'col2'], ['r1_row_id', 'r1_col0', 'r1_col1', 'r1_col2'])}, 'row_id')
    r2 = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'col0', 'col1', 'col2'], ['r2_row_id', 'r2_col0', 'r2_col1', 'r2_col2'])}, 'row_id')
    result = r1
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            rel1_in_db."row_id",
            rel1_in_db."col0",
            rel1_in_db."col1",
            rel1_in_db."col2",
            rel1_in_db."row_id",
            rel1_in_db."col0",
            rel1_in_db."col1",
            rel1_in_db."col2"
        FROM
            rel1_in_db
        WHERE
            rel1_in_db."row_id"=rel1_in_db."row_id"
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TensorToRelation(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=1),
            return_type=relation(schema=[("ci", int), ("cf", float)]),
        )
        def f(x):
            return x

        return udf.registry

    @pytest.fixture(scope="class")
    def udf_args(self):
        return {"x": TensorArg(table_name="tensor_in_db", dtype=int, ndims=1)}

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tensor_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_val" INT)
RETURNS
TABLE("ci" INT,"cf" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['x_dim0', 'x_val'])})
    return udfio.as_relational_table(x, 'row_id')
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tensor_in_db."dim0",
            tensor_in_db."val"
        FROM
            tensor_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("ci", DType.INT),
                    ("cf", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("ci" INT,"cf" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_LiteralArgument(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=DType.INT, ndims=1),
            v=literal(),
            return_type=relation([("result", int)]),
        )
        def f(x, v):
            result = v
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="the_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            42,
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_val" INT)
RETURNS
TABLE("result" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['x_dim0', 'x_val'])})
    v = 42
    result = v
    return udfio.as_relational_table(result, 'row_id')
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            the_table."dim0",
            the_table."val"
        FROM
            the_table
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("result", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("result" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_ManyLiteralArguments(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=DType.INT, ndims=1),
            v=literal(),
            w=literal(),
            return_type=relation([("result", int)]),
        )
        def f(x, v, w):
            result = v + w
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tensor_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            42,
            24,
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_val" INT)
RETURNS
TABLE("result" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['x_dim0', 'x_val'])})
    v = 42
    w = 24
    result = v + w
    return udfio.as_relational_table(result, 'row_id')
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tensor_in_db."dim0",
            tensor_in_db."val"
        FROM
            tensor_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("result", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("result" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_NoArguments(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            return_type=tensor(dtype=int, ndims=1),
        )
        def f():
            x = [1, 2, 3]
            return x

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return []

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("dim0" INT,"val" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = [1, 2, 3]
    return udfio.as_tensor_table(numpy.array(x))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("val", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"val" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_RelationIncludeRowId(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        S = TypeVar("S")

        @udf(r=relation(schema=S), return_type=tensor(dtype=DType.FLOAT, ndims=2))
        def f(r):
            result = r
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="rel_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="c0", dtype=DType.INT),
                        ColumnInfo(name="c1", dtype=DType.FLOAT),
                        ColumnInfo(name="c2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("r_row_id" INT,"r_c0" INT,"r_c1" DOUBLE,"r_c2" VARCHAR(500))
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    r = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'c0', 'c1', 'c2'], ['r_row_id', 'r_c0', 'r_c1', 'r_c2'])}, 'row_id')
    result = r
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            rel_in_db."row_id",
            rel_in_db."c0",
            rel_in_db."c1",
            rel_in_db."c2"
        FROM
            rel_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_RelationExcludeNodeid(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        S = TypeVar("S")

        @udf(r=relation(schema=S), return_type=tensor(dtype=DType.FLOAT, ndims=2))
        def f(r):
            result = r
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="rel_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="c0", dtype=DType.INT),
                        ColumnInfo(name="c1", dtype=DType.FLOAT),
                        ColumnInfo(name="c2", dtype=DType.STR),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("r_row_id" INT,"r_c0" INT,"r_c1" DOUBLE,"r_c2" VARCHAR(500))
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    r = udfio.from_relational_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['row_id', 'c0', 'c1', 'c2'], ['r_row_id', 'r_c0', 'r_c1', 'r_c2'])}, 'row_id')
    result = r
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            rel_in_db."row_id",
            rel_in_db."c0",
            rel_in_db."c1",
            rel_in_db."c2"
        FROM
            rel_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_UnknownReturnDimensions(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        T = TypeVar("S")
        N = TypeVar("N")

        @udf(t=tensor(dtype=T, ndims=N), return_type=tensor(dtype=T, ndims=N))
        def f(t):
            result = t
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tens_in_db",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("t_dim0" INT,"t_dim1" INT,"t_val" INT)
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    t = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'dim1', 'val'], ['t_dim0', 't_dim1', 't_val'])})
    result = t
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tens_in_db."dim0",
            tens_in_db."dim1",
            tens_in_db."val"
        FROM
            tens_in_db
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TwoTensors1DReturnTable(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=1),
            y=tensor(dtype=int, ndims=1),
            return_type=tensor(dtype=int, ndims=1),
        )
        def f(x, y):
            result = x - y
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tens0",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="tens1",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_val" INT,"y_dim0" INT,"y_val" INT)
RETURNS
TABLE("dim0" INT,"val" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['x_dim0', 'x_val'])})
    y = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['y_dim0', 'y_val'])})
    result = x - y
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tens0."dim0",
            tens0."val",
            tens1."dim0",
            tens1."val"
        FROM
            tens0,
            tens1
        WHERE
            tens0."dim0"=tens1."dim0"
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("val", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"val" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_ThreeTensors1DReturnTable(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=1),
            y=tensor(dtype=int, ndims=1),
            z=tensor(dtype=int, ndims=1),
            return_type=tensor(dtype=int, ndims=1),
        )
        def f(x, y, z):
            result = x + y + z
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tens0",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="tens1",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="tens2",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_val" INT,"y_dim0" INT,"y_val" INT,"z_dim0" INT,"z_val" INT)
RETURNS
TABLE("dim0" INT,"val" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['x_dim0', 'x_val'])})
    y = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['y_dim0', 'y_val'])})
    z = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['z_dim0', 'z_val'])})
    result = x + y + z
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tens0."dim0",
            tens0."val",
            tens1."dim0",
            tens1."val",
            tens2."dim0",
            tens2."val"
        FROM
            tens0,
            tens1,
            tens2
        WHERE
            tens0."dim0"=tens1."dim0" AND
            tens0."dim0"=tens2."dim0"
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("val", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"val" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_ThreeTensors2DReturnTable(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            x=tensor(dtype=int, ndims=2),
            y=tensor(dtype=int, ndims=2),
            z=tensor(dtype=int, ndims=2),
            return_type=tensor(dtype=int, ndims=2),
        )
        def f(x, y, z):
            result = x + y + z
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="tens0",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="tens1",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="tens2",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="dim1", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("x_dim0" INT,"x_dim1" INT,"x_val" INT,"y_dim0" INT,"y_dim1" INT,"y_val" INT,"z_dim0" INT,"z_dim1" INT,"z_val" INT)
RETURNS
TABLE("dim0" INT,"dim1" INT,"val" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    x = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'dim1', 'val'], ['x_dim0', 'x_dim1', 'x_val'])})
    y = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'dim1', 'val'], ['y_dim0', 'y_dim1', 'y_val'])})
    z = udfio.from_tensor_table({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'dim1', 'val'], ['z_dim0', 'z_dim1', 'z_val'])})
    result = x + y + z
    return udfio.as_tensor_table(numpy.array(result))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            tens0."dim0",
            tens0."dim1",
            tens0."val",
            tens1."dim0",
            tens1."dim1",
            tens1."val",
            tens2."dim0",
            tens2."dim1",
            tens2."val"
        FROM
            tens0,
            tens1,
            tens2
        WHERE
            tens0."dim0"=tens1."dim0" AND
            tens0."dim1"=tens1."dim1" AND
            tens0."dim0"=tens2."dim0" AND
            tens0."dim1"=tens2."dim1"
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("dim1", DType.INT),
                    ("val", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"dim1" INT,"val" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_MergeTensor(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            xs=MergeTensorType(dtype=int, ndims=1),
            return_type=tensor(dtype=int, ndims=1),
        )
        def sum_tensors(xs):
            x = sum(xs)
            return x

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="merge_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="row_id", dtype=DType.INT),
                        ColumnInfo(name="dim0", dtype=DType.INT),
                        ColumnInfo(name="val", dtype=DType.INT),
                    ]
                ),
                type_=TableType.NORMAL,
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name("xs_dim0" INT,"xs_val" INT)
RETURNS
TABLE("dim0" INT,"val" INT)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    xs = udfio.merge_tensor_to_list({name: _columns[name_w_prefix] for name, name_w_prefix in zip(['dim0', 'val'], ['xs_dim0', 'xs_val'])})
    x = sum(xs)
    return udfio.as_tensor_table(numpy.array(x))
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name((
        SELECT
            merge_table."dim0",
            merge_table."val"
        FROM
            merge_table
    ));"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("dim0", DType.INT),
                    ("val", DType.INT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("dim0" INT,"val" INT);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_StateReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(t=literal(), return_type=state())
        def f(t):
            result = {"num": 5}
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [5]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    t = 5
    result = {'num': 5}
    return pickle.dumps(result)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [state] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = pickle.loads(state)
        assert result == {"num": 5}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_StateInputandReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            t=literal(),
            prev_state=state(),
            return_type=state(),
        )
        def f(t, prev_state):
            prev_state["num"] = prev_state["num"] + t
            return prev_state

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            5,
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    prev_state = pickle.loads(__state_str)
    t = 5
    prev_state['num'] = prev_state['num'] + t
    return pickle.dumps(prev_state)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database", "create_state_table")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [state] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = pickle.loads(state)
        assert result == {"num": 10}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TransferReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(t=literal(), return_type=transfer())
        def f(t):
            result = {"num": t, "list_of_nums": [t, t, t]}
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [5]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import json
    t = 5
    result = {'num': t, 'list_of_nums': [t, t, t]}
    return json.dumps(result)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [transfer] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = json.loads(transfer)
        assert result == {"num": 5, "list_of_nums": [5, 5, 5]}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TransferInputAndReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            t=literal(),
            transfer=transfer(),
            return_type=transfer(),
        )
        def f(t, transfer):
            transfer["num"] = transfer["num"] + t
            return transfer

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            5,
            TableInfo(
                name="test_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import json
    __transfer_str = _conn.execute("SELECT transfer from test_transfer_table;")["transfer"][0]
    transfer = json.loads(__transfer_str)
    t = 5
    transfer['num'] = transfer['num'] + t
    return json.dumps(transfer)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database", "create_transfer_table")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [transfer] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = json.loads(transfer)
        assert result == {"num": 10}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TransferInputAndStateReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            t=literal(),
            transfer=transfer(),
            return_type=state(),
        )
        def f(t, transfer):
            transfer["num"] = transfer["num"] + t
            return transfer

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            5,
            TableInfo(
                name="test_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __transfer_str = _conn.execute("SELECT transfer from test_transfer_table;")["transfer"][0]
    transfer = json.loads(__transfer_str)
    t = 5
    transfer['num'] = transfer['num'] + t
    return pickle.dumps(transfer)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database", "create_transfer_table")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [state] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = pickle.loads(state)
        assert result == {"num": 10}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_TransferAndStateInputandStateReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            t=literal(),
            transfer=transfer(),
            state=state(),
            return_type=state(),
        )
        def f(t, transfer, state):
            result = {}
            result["num"] = transfer["num"] + state["num"] + t
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            5,
            TableInfo(
                name="test_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __transfer_str = _conn.execute("SELECT transfer from test_transfer_table;")["transfer"][0]
    transfer = json.loads(__transfer_str)
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    t = 5
    result = {}
    result['num'] = transfer['num'] + state['num'] + t
    return pickle.dumps(result)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_transfer_table",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [state] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = pickle.loads(state)
        assert result == {"num": 15}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_MergeTransferAndStateInputandTransferReturnType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfers=merge_transfer(),
            state=state(),
            return_type=transfer(),
        )
        def f(transfers, state):
            sum = 0
            for t in transfers:
                sum += t["num"]
            sum += state["num"]
            result = {"num": sum}
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_merge_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __transfer_strs = _conn.execute("SELECT transfer from test_merge_transfer_table;")["transfer"]
    transfers = [json.loads(str) for str in __transfer_strs]
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    sum = 0
    for t in transfers:
        sum += t['num']
    sum += state['num']
    result = {'num': sum}
    return json.dumps(result)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_merge_transfer_table",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [transfer] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = json.loads(transfer)
        assert result == {"num": 20}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_LocalStepLogic(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            state=state(),
            transfer=transfer(),
            return_type=[state(), transfer()],
        )
        def f(state, transfer):
            result1 = {"num": transfer["num"] + state["num"]}
            result2 = {"num": transfer["num"] * state["num"]}
            return result1, result2

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="test_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    __transfer_str = _conn.execute("SELECT transfer from test_transfer_table;")["transfer"][0]
    transfer = json.loads(__transfer_str)
    result1 = {'num': transfer['num'] + state['num']}
    result2 = {'num': transfer['num'] * state['num']}
    _conn.execute(f"INSERT INTO $loopback_table_name_0 VALUES ('{json.dumps(result2)}');")
    return pickle.dumps(result1)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            ),
            UDFGenTableResult(
                tablename_placeholder="loopback_table_name_0",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $loopback_table_name_0;"),
                create_query=Template(
                    'CREATE TABLE $loopback_table_name_0("transfer" CLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_transfer_table",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        (state_,) = globalnode_db_cursor.execute(
            "SELECT state FROM main_output_table_name"
        ).fetchone()
        result1 = pickle.loads(state_)
        assert result1 == {"num": 10}
        (transfer_,) = globalnode_db_cursor.execute(
            "SELECT transfer FROM loopback_table_name_0"
        ).fetchone()
        result2 = json.loads(transfer_)
        assert result2 == {"num": 25}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_LocalStepLogic_Transfer_first_input_and_output(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfer=transfer(),
            state=state(),
            return_type=[transfer(), state()],
        )
        def f(transfer, state):
            result1 = {"num": transfer["num"] + state["num"]}
            result2 = {"num": transfer["num"] * state["num"]}
            return result1, result2

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __transfer_str = _conn.execute("SELECT transfer from test_transfer_table;")["transfer"][0]
    transfer = json.loads(__transfer_str)
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    result1 = {'num': transfer['num'] + state['num']}
    result2 = {'num': transfer['num'] * state['num']}
    _conn.execute(f"INSERT INTO $loopback_table_name_0 VALUES ('{pickle.dumps(result2).hex()}');")
    return json.dumps(result1)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            ),
            UDFGenTableResult(
                tablename_placeholder="loopback_table_name_0",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $loopback_table_name_0;"),
                create_query=Template(
                    'CREATE TABLE $loopback_table_name_0("state" BLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_transfer_table",
        "create_state_table",
    )
    def test_udf_with_globalnode_db_cursor(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        (transfer_,) = globalnode_db_cursor.execute(
            "SELECT transfer FROM main_output_table_name"
        ).fetchone()
        result1 = json.loads(transfer_)
        assert result1 == {"num": 10}
        (state_,) = globalnode_db_cursor.execute(
            "SELECT state FROM loopback_table_name_0"
        ).fetchone()
        result2 = pickle.loads(state_)
        assert result2 == {"num": 25}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_GlobalStepLogic(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            state=state(),
            transfers=merge_transfer(),
            return_type=[state(), transfer()],
        )
        def f(state, transfers):
            sum_transfers = 0
            for transfer in transfers:
                sum_transfers += transfer["num"]
            result1 = {"num": sum_transfers + state["num"]}
            result2 = {"num": sum_transfers * state["num"]}
            return result1, result2

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
            TableInfo(
                name="test_merge_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    __transfer_strs = _conn.execute("SELECT transfer from test_merge_transfer_table;")["transfer"]
    transfers = [json.loads(str) for str in __transfer_strs]
    sum_transfers = 0
    for transfer in transfers:
        sum_transfers += transfer['num']
    result1 = {'num': sum_transfers + state['num']}
    result2 = {'num': sum_transfers * state['num']}
    _conn.execute(f"INSERT INTO $loopback_table_name_0 VALUES ('{json.dumps(result2)}');")
    return pickle.dumps(result1)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            ),
            UDFGenTableResult(
                tablename_placeholder="loopback_table_name_0",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $loopback_table_name_0;"),
                create_query=Template(
                    'CREATE TABLE $loopback_table_name_0("transfer" CLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_merge_transfer_table",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        (state_,) = globalnode_db_cursor.execute(
            "SELECT state FROM main_output_table_name"
        ).fetchone()
        result1 = pickle.loads(state_)
        assert result1 == {"num": 20}
        (transfer_,) = globalnode_db_cursor.execute(
            "SELECT transfer FROM loopback_table_name_0"
        ).fetchone()
        result2 = json.loads(transfer_)
        assert result2 == {"num": 75}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_SecureTransferOutput_with_SMPC_off(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            state=state(),
            return_type=secure_transfer(sum_op=True, min_op=True, max_op=True),
        )
        def f(state):
            result = {
                "sum": {"data": state["num"], "operation": "sum", "type": "int"},
                "min": {"data": state["num"], "operation": "min", "type": "int"},
                "max": {"data": state["num"], "operation": "max", "type": "int"},
            }
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("secure_transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    result = {'sum': {'data': state['num'], 'operation': 'sum', 'type': 'int'},
        'min': {'data': state['num'], 'operation': 'min', 'type': 'int'}, 'max':
        {'data': state['num'], 'operation': 'max', 'type': 'int'}}
    return json.dumps(result)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("secure_transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("secure_transfer" CLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        secure_transfer_, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM main_output_table_name"
        ).fetchone()
        result = json.loads(secure_transfer_)
        assert result == {
            "sum": {"data": 5, "operation": "sum", "type": "int"},
            "min": {"data": 5, "operation": "min", "type": "int"},
            "max": {"data": 5, "operation": "max", "type": "int"},
        }

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_SecureTransferOutput_with_SMPC_on(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            state=state(),
            return_type=secure_transfer(sum_op=True, max_op=True),
        )
        def f(state):
            result = {
                "sum": {"data": state["num"], "operation": "sum", "type": "int"},
                "max": {"data": state["num"], "operation": "max", "type": "int"},
            }
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("secure_transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    result = {'sum': {'data': state['num'], 'operation': 'sum', 'type': 'int'},
        'max': {'data': state['num'], 'operation': 'max', 'type': 'int'}}
    template, sum_op, min_op, max_op = udfio.split_secure_transfer_dict(result)
    _conn.execute(f"INSERT INTO $main_output_table_name_sum_op VALUES ('{json.dumps(sum_op)}');")
    _conn.execute(f"INSERT INTO $main_output_table_name_max_op VALUES ('{json.dumps(max_op)}');")
    return json.dumps(template)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenSMPCResult(
                template=UDFGenTableResult(
                    tablename_placeholder="main_output_table_name",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template(
                        "DROP TABLE IF EXISTS $main_output_table_name;"
                    ),
                    create_query=Template(
                        'CREATE TABLE $main_output_table_name("secure_transfer" CLOB);'
                    ),
                ),
                sum_op_values=UDFGenTableResult(
                    tablename_placeholder="main_output_table_name_sum_op",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template(
                        "DROP TABLE IF EXISTS $main_output_table_name_sum_op;"
                    ),
                    create_query=Template(
                        'CREATE TABLE $main_output_table_name_sum_op("secure_transfer" CLOB);'
                    ),
                ),
                max_op_values=UDFGenTableResult(
                    tablename_placeholder="main_output_table_name_max_op",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template(
                        "DROP TABLE IF EXISTS $main_output_table_name_max_op;"
                    ),
                    create_query=Template(
                        'CREATE TABLE $main_output_table_name_max_op("secure_transfer" CLOB);'
                    ),
                ),
            )
        ]

    @pytest.fixture(scope="class")
    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        template_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM main_output_table_name"
        ).fetchone()
        template = json.loads(template_str)
        assert template == {
            "max": {"data": 0, "operation": "max", "type": "int"},
            "sum": {"data": 0, "operation": "sum", "type": "int"},
        }

        sum_op_values_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM main_output_table_name_sum_op"
        ).fetchone()
        sum_op_values = json.loads(sum_op_values_str)
        assert sum_op_values == [5]

        max_op_values_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM main_output_table_name_max_op"
        ).fetchone()
        max_op_values = json.loads(max_op_values_str)
        assert max_op_values == [5]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=True,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_SecureTransferOutputAs2ndOutput_with_SMPC_off(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            state=state(),
            return_type=[
                state(),
                secure_transfer(sum_op=True, min_op=True, max_op=True),
            ],
        )
        def f(state):
            result = {
                "sum": {"data": state["num"], "operation": "sum", "type": "int"},
                "min": {"data": state["num"], "operation": "min", "type": "int"},
                "max": {"data": state["num"], "operation": "max", "type": "int"},
            }
            return state, result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    result = {'sum': {'data': state['num'], 'operation': 'sum', 'type': 'int'},
        'min': {'data': state['num'], 'operation': 'min', 'type': 'int'}, 'max':
        {'data': state['num'], 'operation': 'max', 'type': 'int'}}
    _conn.execute(f"INSERT INTO $loopback_table_name_0 VALUES ('{json.dumps(result)}');")
    return pickle.dumps(state)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            ),
            UDFGenTableResult(
                tablename_placeholder="loopback_table_name_0",
                table_schema=[
                    ("secure_transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $loopback_table_name_0;"),
                create_query=Template(
                    'CREATE TABLE $loopback_table_name_0("secure_transfer" CLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)

        secure_transfer_, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM loopback_table_name_0"
        ).fetchone()
        result = json.loads(secure_transfer_)
        assert result == {
            "sum": {"data": 5, "operation": "sum", "type": "int"},
            "min": {"data": 5, "operation": "min", "type": "int"},
            "max": {"data": 5, "operation": "max", "type": "int"},
        }

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_SecureTransferOutputAs2ndOutput_with_SMPC_on(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            state=state(),
            return_type=[
                state(),
                secure_transfer(sum_op=True, min_op=True, max_op=True),
            ],
        )
        def f(state):
            result = {
                "sum": {"data": state["num"], "operation": "sum", "type": "int"},
                "min": {"data": state["num"], "operation": "min", "type": "int"},
                "max": {"data": state["num"], "operation": "max", "type": "int"},
            }
            return state, result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_state_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="state", dtype=DType.BINARY),
                    ]
                ),
                type_=TableType.NORMAL,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("state" BLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import pickle
    import json
    __state_str = _conn.execute("SELECT state from test_state_table;")["state"][0]
    state = pickle.loads(__state_str)
    result = {'sum': {'data': state['num'], 'operation': 'sum', 'type': 'int'},
        'min': {'data': state['num'], 'operation': 'min', 'type': 'int'}, 'max':
        {'data': state['num'], 'operation': 'max', 'type': 'int'}}
    template, sum_op, min_op, max_op = udfio.split_secure_transfer_dict(result)
    _conn.execute(f"INSERT INTO $loopback_table_name_0 VALUES ('{json.dumps(template)}');")
    _conn.execute(f"INSERT INTO $loopback_table_name_0_sum_op VALUES ('{json.dumps(sum_op)}');")
    _conn.execute(f"INSERT INTO $loopback_table_name_0_min_op VALUES ('{json.dumps(min_op)}');")
    _conn.execute(f"INSERT INTO $loopback_table_name_0_max_op VALUES ('{json.dumps(max_op)}');")
    return pickle.dumps(state)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("state", DType.BINARY),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("state" BLOB);'
                ),
            ),
            UDFGenSMPCResult(
                template=UDFGenTableResult(
                    tablename_placeholder="loopback_table_name_0",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template("DROP TABLE IF EXISTS $loopback_table_name_0;"),
                    create_query=Template(
                        'CREATE TABLE $loopback_table_name_0("secure_transfer" CLOB);'
                    ),
                ),
                sum_op_values=UDFGenTableResult(
                    tablename_placeholder="loopback_table_name_0_sum_op",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template(
                        "DROP TABLE IF EXISTS $loopback_table_name_0_sum_op;"
                    ),
                    create_query=Template(
                        'CREATE TABLE $loopback_table_name_0_sum_op("secure_transfer" CLOB);'
                    ),
                ),
                min_op_values=UDFGenTableResult(
                    tablename_placeholder="loopback_table_name_0_min_op",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template(
                        "DROP TABLE IF EXISTS $loopback_table_name_0_min_op;"
                    ),
                    create_query=Template(
                        'CREATE TABLE $loopback_table_name_0_min_op("secure_transfer" CLOB);'
                    ),
                ),
                max_op_values=UDFGenTableResult(
                    tablename_placeholder="loopback_table_name_0_max_op",
                    table_schema=[
                        ("secure_transfer", DType.JSON),
                    ],
                    drop_query=Template(
                        "DROP TABLE IF EXISTS $loopback_table_name_0_max_op;"
                    ),
                    create_query=Template(
                        'CREATE TABLE $loopback_table_name_0_max_op("secure_transfer" CLOB);'
                    ),
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_state_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        template_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM loopback_table_name_0"
        ).fetchone()
        template = json.loads(template_str)
        assert template == {
            "sum": {"data": 0, "operation": "sum", "type": "int"},
            "min": {"data": 0, "operation": "min", "type": "int"},
            "max": {"data": 0, "operation": "max", "type": "int"},
        }

        sum_op_values_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM loopback_table_name_0_sum_op"
        ).fetchone()
        sum_op_values = json.loads(sum_op_values_str)
        assert sum_op_values == [5]

        min_op_values_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM loopback_table_name_0_min_op"
        ).fetchone()
        min_op_values = json.loads(min_op_values_str)
        assert min_op_values == [5]

        max_op_values_str, *_ = globalnode_db_cursor.execute(
            "SELECT secure_transfer FROM loopback_table_name_0_max_op"
        ).fetchone()
        max_op_values = json.loads(max_op_values_str)
        assert max_op_values == [5]

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=True,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_SecureTransferInput_with_SMPC_off(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfer=secure_transfer(sum_op=True),
            return_type=transfer(),
        )
        def f(transfer):
            return transfer

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            TableInfo(
                name="test_secure_transfer_table",
                schema_=TableSchema(
                    columns=[
                        ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                    ]
                ),
                type_=TableType.REMOTE,
            ),
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import json
    __transfer_strs = _conn.execute("SELECT secure_transfer from test_secure_transfer_table;")["secure_transfer"]
    __transfers = [json.loads(str) for str in __transfer_strs]
    transfer = udfio.secure_transfers_to_merged_dict(__transfers)
    return json.dumps(transfer)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_secure_transfer_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        transfer, *_ = globalnode_db_cursor.execute(
            "SELECT transfer FROM main_output_table_name"
        ).fetchone()
        result = json.loads(transfer)
        assert result == {"sum": 111}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_SecureTransferInput_with_SMPC_on(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            transfer=secure_transfer(sum_op=True, max_op=True),
            return_type=transfer(),
        )
        def f(transfer):
            return transfer

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [
            SMPCTablesInfo(
                template=TableInfo(
                    name="test_smpc_template_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
                sum_op=TableInfo(
                    name="test_smpc_sum_op_values_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
                max_op=TableInfo(
                    name="test_smpc_max_op_values_table",
                    schema_=TableSchema(
                        columns=[
                            ColumnInfo(name="secure_transfer", dtype=DType.JSON),
                        ]
                    ),
                    type_=TableType.NORMAL,
                ),
            )
        ]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import json
    __template_str = _conn.execute("SELECT secure_transfer from test_smpc_template_table;")["secure_transfer"][0]
    __template = json.loads(__template_str)
    __sum_op_values_str = _conn.execute("SELECT secure_transfer from test_smpc_sum_op_values_table;")["secure_transfer"][0]
    __sum_op_values = json.loads(__sum_op_values_str)
    __min_op_values = None
    __max_op_values_str = _conn.execute("SELECT secure_transfer from test_smpc_max_op_values_table;")["secure_transfer"][0]
    __max_op_values = json.loads(__max_op_values_str)
    transfer = udfio.construct_secure_transfer_dict(__template,__sum_op_values,__min_op_values,__max_op_values)
    return json.dumps(transfer)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            ),
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures(
        "use_globalnode_database",
        "create_smpc_template_table_with_sum_and_max",
        "create_smpc_sum_op_values_table",
        "create_smpc_max_op_values_table",
    )
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        transfer, *_ = globalnode_db_cursor.execute(
            "SELECT transfer FROM main_output_table_name"
        ).fetchone()
        result = json.loads(transfer)
        assert result == {"sum": [100, 200, 300], "max": 58}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=True,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_LoggerArgument(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(
            t=literal(),
            logger=udf_logger(),
            return_type=transfer(),
        )
        def f(t, logger):
            logger.info("Log inside monetdb udf.")
            result = {"num": t}
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def positional_args(self):
        return [5]

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import json
    t = 5
    logger = udfio.get_logger('$udf_name', '$request_id')
    logger.info('Log inside monetdb udf.')
    result = {'num': t}
    return json.dumps(result)
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("transfer", DType.JSON),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("transfer" CLOB);'
                ),
            )
        ]

    @pytest.mark.slow
    @pytest.mark.database
    @pytest.mark.usefixtures("use_globalnode_database")
    def test_udf_with_db(
        self,
        concrete_udf_outputs,
        concrete_udf_def,
        concrete_udf_sel,
        globalnode_db_cursor,
    ):
        globalnode_db_cursor.execute(concrete_udf_outputs)
        globalnode_db_cursor.execute(concrete_udf_def)
        globalnode_db_cursor.execute(concrete_udf_sel)
        [transfer] = globalnode_db_cursor.execute(
            "SELECT * FROM main_output_table_name"
        ).fetchone()
        result = json.loads(transfer)
        assert result == {"num": 5}

    def test_generate_udf_queries(
        self,
        funcname,
        positional_args,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=positional_args,
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel

        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results, expected_udf_outputs
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_DeferredOutputSchema(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(return_type=relation(schema=DEFERRED))
        def f():
            result = {"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]}
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("a" INT,"b" DOUBLE)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    result = {'a': [1, 2, 3], 'b': [4.0, 5.0, 6.0]}
    return udfio.as_relational_table(result, 'row_id')
}"""

    @pytest.fixture(scope="class")
    def expected_udfsel(self):
        return """\
INSERT INTO $main_output_table_name
SELECT
    *
FROM
    $udf_name();"""

    @pytest.fixture(scope="class")
    def expected_udf_outputs(self):
        return [
            UDFGenTableResult(
                tablename_placeholder="main_output_table_name",
                table_schema=[
                    ("a", DType.INT),
                    ("b", DType.FLOAT),
                ],
                drop_query=Template("DROP TABLE IF EXISTS $main_output_table_name;"),
                create_query=Template(
                    'CREATE TABLE $main_output_table_name("a" INT,"b" DOUBLE);'
                ),
            )
        ]

    def test_generate_udf_queries(
        self,
        funcname,
        expected_udfdef,
        expected_udfsel,
        expected_udf_outputs,
    ):
        output_schema = [("a", DType.INT), ("b", DType.FLOAT)]
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=[],
            keyword_args={},
            smpc_used=False,
            output_schema=output_schema,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef
        assert udf_execution_queries.udf_select_query.template == expected_udfsel
        for udf_output, expected_udf_output in zip(
            udf_execution_queries.udf_results,
            expected_udf_outputs,
        ):
            assert udf_output == expected_udf_output


class TestUDFGen_PlaceholderInputType(TestUDFGenBase):
    @pytest.fixture(scope="class")
    def udfregistry(self):
        @udf(a=placeholder("some_name"), return_type=transfer())
        def f(a):
            result = {"a": a}
            return result

        return udf.registry

    @pytest.fixture(scope="class")
    def expected_udfdef(self):
        return """\
CREATE OR REPLACE FUNCTION
$udf_name()
RETURNS
TABLE("transfer" CLOB)
LANGUAGE PYTHON
{
    import pandas as pd
    import udfio
    import json
    a = $some_name
    result = {'a': a}
    return json.dumps(result)
}"""

    def test_generate_udf_queries(
        self,
        funcname,
        expected_udfdef,
    ):
        udf_execution_queries = generate_udf_queries(
            func_name=funcname,
            positional_args=[],
            keyword_args={},
            smpc_used=False,
        )
        assert udf_execution_queries.udf_definition_query.template == expected_udfdef


class N:
    ...


def test_get_create_design_matrix_select_only_numerical():
    enums = {}
    numerical_vars = ["n1", "n2"]
    design_matrix = N()
    design_matrix.name = "test_table"
    args = {
        "x": design_matrix,
        "enums": enums,
        "numerical_vars": numerical_vars,
        "intercept": True,
    }
    expected = """\
INSERT INTO $main_output_table_name
SELECT
    "row_id",
    1 AS "intercept",
    "n1",
    "n2"
FROM
    test_table;"""
    result = get_create_dummy_encoded_design_matrix_execution_queries(args)
    assert result.udf_select_query.template == expected


def test_get_create_design_matrix_select_only_categorical():
    enums = {
        "c1": [{"code": "l1", "dummy": "c1__1"}, {"code": "l2", "dummy": "c1__2"}],
    }
    numerical_vars = []
    design_matrix = N()
    design_matrix.name = "test_table"
    args = {
        "x": design_matrix,
        "enums": enums,
        "numerical_vars": numerical_vars,
        "intercept": True,
    }
    expected = """\
INSERT INTO $main_output_table_name
SELECT
    "row_id",
    1 AS "intercept",
    CASE WHEN c1 = 'l1' THEN 1 ELSE 0 END AS "c1__1",
    CASE WHEN c1 = 'l2' THEN 1 ELSE 0 END AS "c1__2"
FROM
    test_table;"""
    result = get_create_dummy_encoded_design_matrix_execution_queries(args)
    assert result.udf_select_query.template == expected


def test_get_create_design_matrix_select_no_intercept():
    enums = {
        "c1": [{"code": "l1", "dummy": "c1__1"}, {"code": "l2", "dummy": "c1__2"}],
    }
    numerical_vars = []
    design_matrix = N()
    design_matrix.name = "test_table"
    args = {
        "x": design_matrix,
        "enums": enums,
        "numerical_vars": numerical_vars,
        "intercept": False,
    }
    expected = """\
INSERT INTO $main_output_table_name
SELECT
    "row_id",
    CASE WHEN c1 = 'l1' THEN 1 ELSE 0 END AS "c1__1",
    CASE WHEN c1 = 'l2' THEN 1 ELSE 0 END AS "c1__2"
FROM
    test_table;"""
    result = get_create_dummy_encoded_design_matrix_execution_queries(args)
    assert result.udf_select_query.template == expected


def test_get_create_design_matrix_select_full():
    enums = {
        "c1": [{"code": "l1", "dummy": "c1__1"}, {"code": "l2", "dummy": "c1__2"}],
        "c2": [
            {"code": "A", "dummy": "c2__1"},
            {"code": "B", "dummy": "c2__2"},
            {"code": "C", "dummy": "c2__3"},
        ],
    }
    numerical_vars = ["n1", "n2"]
    design_matrix = N()
    design_matrix.name = "test_table"
    args = {
        "x": design_matrix,
        "enums": enums,
        "numerical_vars": numerical_vars,
        "intercept": True,
    }
    expected = """\
INSERT INTO $main_output_table_name
SELECT
    "row_id",
    1 AS "intercept",
    CASE WHEN c1 = 'l1' THEN 1 ELSE 0 END AS "c1__1",
    CASE WHEN c1 = 'l2' THEN 1 ELSE 0 END AS "c1__2",
    CASE WHEN c2 = 'A' THEN 1 ELSE 0 END AS "c2__1",
    CASE WHEN c2 = 'B' THEN 1 ELSE 0 END AS "c2__2",
    CASE WHEN c2 = 'C' THEN 1 ELSE 0 END AS "c2__3",
    "n1",
    "n2"
FROM
    test_table;"""
    result = get_create_dummy_encoded_design_matrix_execution_queries(args)
    assert result.udf_select_query.template == expected


def test_get_create_design_matrix_create_query():
    enums = {
        "c1": [{"code": "l1", "dummy": "c1__1"}, {"code": "l2", "dummy": "c1__2"}],
        "c2": [
            {"code": "A", "dummy": "c2__1"},
            {"code": "B", "dummy": "c2__2"},
            {"code": "C", "dummy": "c2__3"},
        ],
    }
    numerical_vars = ["n1", "n2"]
    design_matrix = N()
    design_matrix.name = "test_table"
    args = {
        "x": design_matrix,
        "enums": enums,
        "numerical_vars": numerical_vars,
        "intercept": True,
    }
    expected = 'CREATE TABLE $main_output_table_name("row_id" INT,"intercept" DOUBLE,"c1__1" DOUBLE,"c1__2" DOUBLE,"c2__1" DOUBLE,"c2__2" DOUBLE,"c2__3" DOUBLE,"n1" DOUBLE,"n2" DOUBLE);'
    result = get_create_dummy_encoded_design_matrix_execution_queries(args)
    assert result.udf_results[0].create_query.template == expected
