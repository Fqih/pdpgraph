# SPDX-License-Identifier: Apache-2.0
"""models-aux HTTP API (05 §4): /embed, /rerank, /nli with dynamic batching. Internal only."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated, Any, Literal

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from starlette.exceptions import HTTPException

from models_aux.batching import Batcher
from models_aux.models import Models
from models_aux.settings import ModelsAuxSettings

log = structlog.get_logger()

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


class _ModelFailureError(Exception):
    pass


def _envelope(request: Request, status: int, code: str, message: str, **details: Any) -> Response:
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request.state.request_id,
            "details": details,
        }
    }
    return JSONResponse(body, status_code=status)


def create_app(models: Models, settings: ModelsAuxSettings) -> FastAPI:
    text = Annotated[str, StringConstraints(min_length=1, max_length=settings.max_chars)]
    many = settings.max_inputs

    class _Body(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class EmbedRequest(_Body):
        inputs: list[text] = Field(min_length=1, max_length=many)
        kind: Literal["query", "passage"]  # bge-m3 needs no query/passage prefix

    class RerankRequest(_Body):
        query: text
        passages: list[text] = Field(min_length=1, max_length=many)

    class Pair(_Body):
        premise: text
        hypothesis: text

    class NliRequest(_Body):
        pairs: list[Pair] = Field(min_length=1, max_length=many)

    size, wait = settings.max_batch, settings.max_wait_ms
    embed_b = Batcher(models.embed, max_batch=size, max_wait_ms=wait)
    rerank_b = Batcher(models.rerank, max_batch=size, max_wait_ms=wait)
    nli_b = Batcher(models.nli, max_batch=size, max_wait_ms=wait)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for batcher in (embed_b, rerank_b, nli_b):
                await stack.enter_async_context(batcher)
            yield

    app = FastAPI(title="models-aux", lifespan=lifespan)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id", "")
        try:
            rid = str(uuid.UUID(rid))
        except ValueError:
            rid = str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> Response:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return _envelope(
            request, 422, "invalid_request", "request failed validation", errors=errors
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return _envelope(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(_ModelFailureError)
    async def model_failure(request: Request, _exc: _ModelFailureError) -> Response:
        return _envelope(request, 500, "internal_error", "model inference failed")

    async def run[I, O](batcher: Batcher[I, O], items: Sequence[I], task: str) -> list[O]:
        try:
            return await batcher.submit(items)
        except Exception:
            log.exception("model_failed", task=task)
            raise _ModelFailureError from None

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}  # models load before the server starts

    @app.post("/embed")
    async def embed(req: EmbedRequest) -> dict[str, Any]:
        vectors = await run(embed_b, req.inputs, "embed")
        return {"model": models.names["embed"], "dim": models.dim, "vectors": vectors}

    @app.post("/rerank")
    async def rerank(req: RerankRequest) -> dict[str, Any]:
        scores = await run(rerank_b, [(req.query, p) for p in req.passages], "rerank")
        return {"model": models.names["rerank"], "scores": scores}

    @app.post("/nli")
    async def nli(req: NliRequest) -> dict[str, Any]:
        results = await run(nli_b, [(p.premise, p.hypothesis) for p in req.pairs], "nli")
        return {"model": models.names["nli"], "results": results}

    return app
