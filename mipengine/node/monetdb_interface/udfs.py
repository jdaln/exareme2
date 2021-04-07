from mipengine.node.monetdb_interface.common_actions import connection
from mipengine.node.monetdb_interface.common_actions import cursor


def run_udf(udf_creation_stmt: str,
            udf_execution_query: str,
            ):

    if udf_creation_stmt:
        cursor.execute(udf_creation_stmt)
    cursor.execute(udf_execution_query)
    connection.commit()
