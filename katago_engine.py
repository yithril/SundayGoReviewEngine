import asyncio
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class KataGoEngineError(RuntimeError):
    """Raised when the KataGo engine has died or is unavailable."""

    pass


class KataGoEngine:
    def __init__(self, binary: str, model: str, config: str, max_concurrent: int = 4):
        self.binary = binary
        self.model = model
        self.config = config
        self.max_concurrent = max_concurrent
        self.process: Optional[asyncio.subprocess.Process] = None
        self._concurrency_limit = asyncio.Semaphore(max_concurrent)
        self._pending: dict[str, asyncio.Queue] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._dead = False

    async def start(self):
        logger.info("Starting KataGo...")
        self.process = await asyncio.create_subprocess_exec(
            self.binary,
            "analysis",
            "-config", self.config,
            "-model", self.model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._dead = False
        self._pending = {}
        self._reader_task = asyncio.create_task(self._read_loop())
        # Give KataGo time to load the model before accepting requests
        await asyncio.sleep(5)
        logger.info("KataGo ready")

    async def _read_loop(self):
        """Background task: read KataGo stdout and route responses by id."""
        try:
            while self.process and self.process.stdout:
                raw = await self.process.stdout.readline()
                if not raw:
                    logger.error("KataGo stdout closed unexpectedly")
                    self._signal_dead()
                    break

                try:
                    resp = json.loads(raw.decode().strip())
                except json.JSONDecodeError as e:
                    logger.warning("KataGo sent malformed JSON, skipping: %s", e)
                    continue

                query_id = resp.get("id")
                if query_id is None:
                    logger.warning("KataGo response missing 'id', skipping")
                    continue

                q = self._pending.get(query_id)
                if q is not None:
                    await q.put(resp)
                else:
                    logger.debug("KataGo response for unknown id %r, skipping", query_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Reader loop failed: %s", e)
            self._signal_dead()

    async def is_available(self) -> bool:
        """Return True if the engine can accept a new request without waiting."""
        if self._dead:
            return False
        try:
            await asyncio.wait_for(self._concurrency_limit.acquire(), timeout=0)
            self._concurrency_limit.release()
            return True
        except asyncio.TimeoutError:
            return False

    def _signal_dead(self):
        """Mark engine dead and wake all pending callers so they fail fast."""
        self._dead = True
        for q in self._pending.values():
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def analyze(
        self,
        query: dict,
        num_turns: int,
        on_progress: Optional[Callable] = None,
    ) -> dict[int, dict]:
        """
        Send a query to KataGo and collect responses for all turns.
        Returns a dict mapping turn_number -> KataGo response object.
        """
        if self._dead:
            raise KataGoEngineError("KataGo engine is not available")

        if not self.process or not self.process.stdin:
            raise KataGoEngineError("KataGo process not started")

        query_id = query["id"]
        q: asyncio.Queue = asyncio.Queue()

        async with self._concurrency_limit:
            if self._dead:
                raise KataGoEngineError("KataGo engine is not available")

            self._pending[query_id] = q
            try:
                line = json.dumps(query) + "\n"
                self.process.stdin.write(line.encode())
                await self.process.stdin.drain()

                responses: dict[int, dict] = {}
                while len(responses) < num_turns:
                    resp = await q.get()
                    if resp is None:
                        raise KataGoEngineError("KataGo engine died during analysis")
                    turn = resp["turnNumber"]
                    responses[turn] = resp
                    if on_progress:
                        await on_progress(len(responses) / num_turns)
                return responses
            finally:
                self._pending.pop(query_id, None)

    async def stop(self):
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self.process:
            self.process.terminate()
            await self.process.wait()
            logger.info("KataGo stopped")
        self._dead = True
