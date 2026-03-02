import asyncio
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class KataGoEngineError(RuntimeError):
    """Raised when the KataGo engine has died or is unavailable."""

    pass


class KataGoEngine:
    def __init__(self, binary: str, model: str, config: str):
        self.binary = binary
        self.model = model
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._analyze_lock = asyncio.Lock()
        self._current_queue: Optional[asyncio.Queue] = None
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
        self._current_queue = None
        self._reader_task = asyncio.create_task(self._read_loop())
        # Give KataGo time to load the model before accepting requests
        await asyncio.sleep(5)
        logger.info("KataGo ready")

    async def _read_loop(self):
        """Background task: read KataGo stdout and put responses into the current request's queue."""
        try:
            while self.process and self.process.stdout:
                raw = await self.process.stdout.readline()
                if not raw:
                    logger.error("KataGo stdout closed unexpectedly")
                    self._signal_dead()
                    break

                raw_str = raw.decode().strip()
                raw_preview = raw_str[:200] + "..." if len(raw_str) > 200 else raw_str
                logger.info("read_loop: raw line (truncated): %r", raw_preview)

                try:
                    resp = json.loads(raw_str)
                except json.JSONDecodeError as e:
                    logger.warning("KataGo sent malformed JSON, skipping: %s", e)
                    continue

                if self._current_queue is not None:
                    await self._current_queue.put(resp)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Reader loop failed: %s", e)
            self._signal_dead()

    def status(self) -> str:
        """Return 'running', 'dead', or 'stopped' for health checks."""
        if not self.process:
            return "stopped"
        if self._dead:
            return "dead"
        return "running"

    def _signal_dead(self):
        """Mark engine dead and wake the pending caller so it fails fast."""
        self._dead = True
        if self._current_queue is not None:
            try:
                self._current_queue.put_nowait(None)
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

        async with self._analyze_lock:
            logger.info("analyze: lock acquired query_id=%r num_turns=%s", query_id, num_turns)
            if self._dead:
                raise KataGoEngineError("KataGo engine is not available")

            self._current_queue = q
            try:
                line = json.dumps(query) + "\n"
                self.process.stdin.write(line.encode())
                await self.process.stdin.drain()
                logger.info("analyze: query written to stdin query_id=%r", query_id)

                responses: dict[int, dict] = {}
                while len(responses) < num_turns:
                    logger.info("analyze: awaiting q.get() for query_id=%r", query_id)
                    resp = await q.get()
                    if resp is None:
                        raise KataGoEngineError("KataGo engine died during analysis")
                    if resp.get("error"):
                        raise KataGoEngineError(f"KataGo error: {resp['error']}")
                    turn = resp.get("turnNumber")
                    if turn is None:
                        raise KataGoEngineError(
                            f"KataGo response missing turnNumber (id={query_id}): {resp!r}"
                        )
                    logger.info("analyze: received response query_id=%r turn=%s", query_id, turn)
                    responses[turn] = resp
                    if on_progress:
                        await on_progress(len(responses) / num_turns)
                logger.info("analyze: returning responses for query_id=%r", query_id)
                return responses
            finally:
                self._current_queue = None

    async def stop(self):
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self.process:
            try:
                if self.process.returncode is None:
                    self.process.terminate()
                    await self.process.wait()
            except ProcessLookupError:
                pass  # process already exited (e.g. during restart)
            logger.info("KataGo stopped")
        self._dead = True
