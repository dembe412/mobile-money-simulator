"""
Asynchronous message processing for account operations.
Withdraw and deposit requests are enqueued and processed by background workers.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import asyncio
import logging

from src.core.idempotency import RequestIdempotency
from src.core.operations import AccountOperations

logger = logging.getLogger(__name__)


@dataclass
class OperationMessage:
    """Message payload for async operation processing."""
    request_id: str
    operation_type: str  # withdraw | deposit
    account_id: int
    phone_number: str
    amount: Decimal


class AsyncOperationProcessor:
    """In-memory async message processor for deposit/withdraw operations."""

    def __init__(self, db_session_factory, worker_count: int = 2):
        self.db_session_factory = db_session_factory
        self.worker_count = worker_count
        self.queue: asyncio.Queue[OperationMessage] = asyncio.Queue()
        self._worker_tasks = []
        self._started = False

    async def start(self):
        """Start background workers."""
        if self._started:
            return
        self._started = True
        for idx in range(self.worker_count):
            task = asyncio.create_task(self._worker_loop(idx + 1))
            self._worker_tasks.append(task)
        logger.info(f"Async operation processor started with {self.worker_count} workers")

    async def stop(self):
        """Stop background workers."""
        if not self._started:
            return

        for task in self._worker_tasks:
            task.cancel()

        await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        self._worker_tasks.clear()
        self._started = False
        logger.info("Async operation processor stopped")

    async def enqueue(self, message: OperationMessage):
        """Enqueue an operation message for async processing."""
        if not self._started:
            raise RuntimeError("AsyncOperationProcessor is not started")
        await self.queue.put(message)
        logger.debug(
            "Enqueued %s request %s for account %s",
            message.operation_type,
            message.request_id,
            message.account_id,
        )

    def queue_size(self) -> int:
        """Current queue depth."""
        return self.queue.qsize()

    async def _worker_loop(self, worker_id: int):
        """Background worker for processing queued operations."""
        logger.info(f"Async worker-{worker_id} started")
        try:
            while True:
                message = await self.queue.get()
                try:
                    await self._process_message(message)
                except Exception as exc:
                    logger.error(
                        "Worker-%s failed to process request %s: %s",
                        worker_id,
                        message.request_id,
                        exc,
                        exc_info=True,
                    )
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Async worker-{worker_id} stopped")
            raise

    async def _process_message(self, message: OperationMessage):
        """Process a single queued message using an isolated DB session."""
        db = self.db_session_factory()
        try:
            # Mark as processing before running the operation.
            RequestIdempotency.update_request_status(
                db,
                message.request_id,
                status="processing",
                response_code=202,
                response_data={"status": "processing"},
            )

            if message.operation_type == "withdraw":
                success, result_message, response_data = AccountOperations.withdraw(
                    db,
                    message.account_id,
                    message.phone_number,
                    message.amount,
                    message.request_id,
                )
            elif message.operation_type == "deposit":
                success, result_message, response_data = AccountOperations.deposit(
                    db,
                    message.account_id,
                    message.phone_number,
                    message.amount,
                    message.request_id,
                )
            else:
                success, result_message, response_data = (
                    False,
                    f"Unsupported operation type: {message.operation_type}",
                    {},
                )

            RequestIdempotency.update_request_status(
                db,
                message.request_id,
                status="completed" if success else "failed",
                response_code=200 if success else 400,
                response_data=response_data,
                error_message=None if success else result_message,
            )

            logger.info(
                "Processed async %s request %s: %s",
                message.operation_type,
                message.request_id,
                "success" if success else "failed",
            )
        except Exception as exc:
            logger.error(
                "Unexpected async processing error for %s: %s",
                message.request_id,
                exc,
                exc_info=True,
            )
            RequestIdempotency.update_request_status(
                db,
                message.request_id,
                status="failed",
                response_code=500,
                response_data={},
                error_message=str(exc),
            )
        finally:
            db.close()
