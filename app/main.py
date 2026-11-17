"""FastAPI entrypoint.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 4000
Docs: http://localhost:4000/docs
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import AnalysisError
from app.schemas import AnalyzeRequest, AnalyzeResponse, ErrorResponse
from app.services.analysis_service import analyze_website

app = FastAPI(
    title="AI-Powered Website Link Analysis API",
    description="Analyses a website with an LLM: competitors, search queries, SEO, services and audience.",
    version="1.0.0",
)


@app.exception_handler(AnalysisError)
async def analysis_error_handler(_: Request, exc: AnalysisError):
    body = ErrorResponse(error=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    body = ErrorResponse(error="invalid_request", message='Body must be JSON like {"url": "https://example.com"}.')
    return JSONResponse(status_code=422, content=body.model_dump())


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.post(
    "/link-analysis",
    response_model=AnalyzeResponse,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    tags=["analysis"],
)
async def link_analysis(req: AnalyzeRequest):
    return await analyze_website(req.url)
