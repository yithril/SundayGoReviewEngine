import asyncio
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class KataGoEngine:
    def __init__(self, binary: str, model: str, config: str):
        self.binary = binary
        self.model = model
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()

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
        # Give KataGo time to load the model before accepting requests
        await asyncio.sleep(5)
        logger.info("KataGo ready")

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
        async with self._lock:
            line = json.dumps(query) + "\n"
            self.process.stdin.write(line.encode())
            await self.process.stdin.drain()

            responses: dict[int, dict] = {}
            job_id = query["id"]

            while len(responses) < num_turns:
                raw = await self.process.stdout.readline()
                if not raw:
                    logger.error("KataGo stdout closed unexpectedly")
                    break
                try:
                    resp = json.loads(raw.decode().strip())
                    if resp.get("id") == job_id:
                        turn = resp["turnNumber"]
                        responses[turn] = resp
                        if on_progress:
                            await on_progress(len(responses) / num_turns)
                except (json.JSONDecodeError, KeyError):
                    continue

            return responses

    async def stop(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()
            logger.info("KataGo stopped")
