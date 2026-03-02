import aiosqlite
import json
import uuid
from datetime import datetime
from typing import Optional

DB_PATH = "katago_jobs.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id       TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'queued',
                mode         TEXT NOT NULL DEFAULT 'quick',
                progress     REAL NOT NULL DEFAULT 0.0,
                sgf          TEXT NOT NULL,
                result_json  TEXT,
                error        TEXT,
                created_at   TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        await db.commit()


async def create_job(sgf: str, mode: str) -> str:
    job_id = uuid.uuid4().hex[:10]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO jobs (job_id, mode, sgf, created_at) VALUES (?, ?, ?, ?)",
            (job_id, mode, sgf, datetime.utcnow().isoformat()),
        )
        await db.commit()
    return job_id


async def get_job(job_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_processing(job_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status = 'processing', progress = 0.0 WHERE job_id = ?",
            (job_id,),
        )
        await db.commit()


async def update_progress(job_id: str, progress: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET progress = ? WHERE job_id = ?",
            (round(progress, 3), job_id),
        )
        await db.commit()


async def complete_job(job_id: str, result: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status = 'complete', progress = 1.0, "
            "result_json = ?, completed_at = ? WHERE job_id = ?",
            (json.dumps(result), datetime.utcnow().isoformat(), job_id),
        )
        await db.commit()


async def fail_job(job_id: str, error: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status = 'failed', error = ? WHERE job_id = ?",
            (error, job_id),
        )
        await db.commit()


async def get_next_queued_job() -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_queue_depth() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'processing')"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_queue_position(job_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT COUNT(*) FROM jobs
               WHERE status = 'queued'
               AND created_at <= (SELECT created_at FROM jobs WHERE job_id = ?)""",
            (job_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 1
