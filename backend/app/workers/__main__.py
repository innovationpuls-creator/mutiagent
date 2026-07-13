from app.workers.knowledge_base_worker import run_worker

run_worker(poll_seconds=2.0)
