import asyncio
import unittest
from unittest.mock import Mock

from exareme2.controller.services.api.algorithm_request_dtos import (
    AlgorithmInputDataDTO,
)
from exareme2.controller.services.flower import FlowerIORegistry
from exareme2.controller.services.flower.flower_io_registry import Status


class TestFlowerExecutionInfo(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()  # Create a new event loop
        asyncio.set_event_loop(
            self.loop
        )  # Set the newly created event loop as the current event loop

        self.logger = Mock()
        self.info = FlowerIORegistry(self.logger)

    def tearDown(self):
        self.loop.close()  # Close the loop at the end of the test

    def test_reset_sync_initial_state(self):
        self.info.reset_sync()
        self.assertEqual(self.info.get_status(), Status.RUNNING)
        self.assertFalse(self.info.result_ready.is_set())

    def test_set_result_success(self):
        result = {"data": "some value"}
        asyncio.run(self.info.set_result(result))
        self.assertEqual(self.info.get_status(), Status.SUCCESS)
        self.assertTrue(self.info.result_ready.is_set())

    def test_set_result_failure(self):
        result = {"error": "some error"}
        asyncio.run(self.info.set_result(result))
        self.assertEqual(self.info.get_status(), Status.FAILURE)

    def test_get_result(self):
        result = {"data": "expected result"}
        asyncio.run(self.info.set_result(result))
        retrieved_result = asyncio.run(self.info.get_result())
        self.assertEqual(retrieved_result, result)

    def test_set_inputdata(self):
        new_data = AlgorithmInputDataDTO(
            data_model="new model", datasets=["new dataset"]
        )
        self.info.set_inputdata(new_data)
        self.assertEqual(self.info.get_status(), Status.RUNNING)
        self.assertEqual(self.info.get_inputdata(), new_data)


class TestFlowerExecutionInfoAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.logger = Mock()
        self.info = FlowerIORegistry(self.logger)

    async def test_event_set_on_result(self):
        """Test that the event is set when the result is set."""
        result = {"data": "some value"}
        await self.info.set_result(result)
        self.assertTrue(
            self.info.result_ready.is_set(), "Event should be set after result is set"
        )

    async def test_get_result_waits_for_event(self):
        """Test that get_result waits for the event to be set."""
        result = {"data": "expected result"}
        # Start setting the result in the background
        await self.info.set_result(result)

        # Now retrieve the result, should wait for the set_result to complete
        retrieved_result = await self.info.get_result()
        self.assertEqual(retrieved_result, result)

    async def test_event_reset_on_reset(self):
        """Test that the event is reset when the info is reset."""
        await self.info.reset()
        self.assertFalse(
            self.info.result_ready.is_set(), "Event should be reset after calling reset"
        )

    async def test_get_result_timeout_with_logging_and_error_handling(self):
        """Test that getting the result logs an error, re-raises a timeout error, and sets the error in the result when not set within the timeout period."""
        timeout_duration = 0.1

        # We are no longer expecting a TimeoutError to be raised here as it is caught in the method.
        result = await self.info.get_result_with_timeout(timeout_duration)

        # Verify the logger was called with an error message about the timeout
        expected_error_message = f"Failed to get result: operation timed out after {timeout_duration} seconds"
        self.logger.error.assert_called_with(expected_error_message)

        # Check that the result contains the correct error message
        self.assertEqual(result["error"], expected_error_message)
