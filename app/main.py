from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.deps import get_session
from app.domain.errors import DomainError
from app.routes import admin, lookups
from app.schemas import ErrorBody, ErrorOut


def _error_response(
    status_code: int, code: str, message: str, details: dict
) -> JSONResponse:
    body = ErrorOut(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(lookups.router)
    app.include_router(admin.router)

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request, exc: DomainError):
        return _error_response(
            status_code=exc.status, code=exc.code, message=str(exc), details=exc.details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request, exc: StarletteHTTPException):
        detail = exc.detail
        code: str
        message: str
        details: dict[str, Any]
        if isinstance(detail, dict):
            code = detail.get("code", "http_error")
            message = detail.get("message", "An HTTP error occurred")
            details = detail.get("details", {})
        else:
            code, message, details = "http_error", str(detail), {}
        return _error_response(
            status_code=exc.status_code, code=code, message=message, details=details
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request, exc: RequestValidationError):
        return _error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details={"errors": jsonable_encoder(exc.errors())},
        )

    @app.get("/healthz")
    def healthz():
        # liveness + db connection check
        gen = get_session()
        session = next(gen)
        try:
            session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        finally:
            gen.close()
        return {"status": "ok" if db_ok else "error", "db": db_ok}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
