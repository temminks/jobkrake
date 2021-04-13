import asyncio
import inspect
from typing import Coroutine, Dict, List

from quart import Quart, jsonify, Response

import sources.sources as s
from sources.jobs import Job

app = Quart(__name__)

source_names = [name for name, _ in inspect.getmembers(s, predicate=inspect.iscoroutinefunction) if
                name not in ['parse_rexx', 'parse_workday', 'parse_personio']]


@app.route('/<company>')
async def single_company(company: str) -> Response:
    if company in source_names:
        jobs: Dict[str, List[Job]]
        jobs, _ = await getattr(s, company)()
        response = jsonify({"jobs": jobs})
        response.status_code = 200
    else:
        response = jsonify({"error": "company not found"})
        response.status_code = 404

    return response


@app.route('/')
async def get_jobs() -> Response:
    durations: Dict[str, float] = dict()
    jobs: Dict[str, List[Job]] = dict()
    sources: List[Coroutine] = [getattr(s, source_name)() for source_name in source_names]
    for job in asyncio.as_completed(sources):
        result: Dict[str, List[Job]]
        result, duration = await job
        jobs.update(result)
        durations.update({list(result.keys())[0]: duration})

    response = jsonify({"durations": durations, "jobs": jobs})
    response.status_code = 200
    return response


if __name__ == '__main__':
    app.run(host='localhost', port=8080)
