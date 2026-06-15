from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.deps import get_session
from app.domain.errors import DomainError
from app.routes import lookups


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(lookups.router)

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status,
            content={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
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
