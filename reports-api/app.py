from fastapi import FastAPI, Header, HTTPException, Response, status

app = FastAPI(title="reports-api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reports-api"}


@app.get("/reports")
async def get_report(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    report_content = b"date,user,action\n2026-03-01,prothetic1,download_report\n"

    return Response(
        content=report_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="usage-report.csv"',
        },
    )