from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from plan_route.api.constraints import router as constraints_router
from plan_route.api.health import router as health_router
from plan_route.api.projects import InvalidInputResponse, ValidationIssue
from plan_route.api.projects import router as projects_router
from plan_route.api.routing import router as routing_router

app = FastAPI(
    title="plan_route",
    version="0.1.0",
    description="Research tool using public sources and synthetic buildings only.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
    expose_headers=["X-Project-Revision", "X-Project-Updated-At", "ETag"],
)
app.include_router(health_router)
app.include_router(projects_router)
app.include_router(constraints_router)
app.include_router(routing_router)


@app.exception_handler(RequestValidationError)
async def invalid_input_handler(
    _request, error: RequestValidationError
) -> JSONResponse:
    response = InvalidInputResponse(
        message="Project input failed validation",
        details=[
            ValidationIssue(
                location=list(issue["loc"]),
                message=issue["msg"],
                type=issue["type"],
            )
            for issue in error.errors()
        ],
    )
    return JSONResponse(status_code=422, content=response.model_dump())
