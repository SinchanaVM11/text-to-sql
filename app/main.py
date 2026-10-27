
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.db.database import execute_read_only, initialize_database
from app.db.schema import get_schema
from app.services.hallucination_detector import check_result_sanity
from app.services.sql_generator import SQLGenerationError, generate_sql
from app.services.schema_planner import plan_schema
from app.services.sql_guardrails import SQLGuardrailError, validate_sql


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Text-to-SQL with Guardrails",
    description=(
        "A schema-aware natural-language SQL API "
        "with query safety checks."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    sql: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/schema")
def schema():
    return get_schema()


@app.post("/v1/query")
def query(request: QueryRequest):
    start = perf_counter()

    try:
        # Get the current database schema and permitted table names.
        current_schema = get_schema()
        allowed_tables = {
            table["name"]
            for table in current_schema["tables"]
        }

        planning = None

        if request.sql is not None:
            # Caller-supplied SQL still goes through the same guardrails.
            sql = validate_sql(request.sql, allowed_tables)
        else:
            # Plan against the live schema before generating SQL.
            planning = plan_schema(request.question, current_schema)

            try:
                generated = generate_sql(
                    request.question,
                    planning["schema"],
                )
            except SQLGenerationError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=str(exc),
                ) from exc

            # Always validate against the full live database table allowlist.
            sql = validate_sql(
                generated["sql"],
                allowed_tables,
            )

        # Execute only after validation.
        columns, rows = execute_read_only(sql)

        sanity = check_result_sanity(
            request.question,
            sql,
            rows,
            columns,
        )

        return {
            "question": request.question,
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "latency_ms": round(
                (perf_counter() - start) * 1000,
                2,
            ),
            "sanity_check": sanity,
            "planning": (
                {
                    "selected_tables": planning["selected_tables"],
                    "matched_terms": planning["matched_terms"],
                    "strategy": planning["strategy"],
                }
                if planning is not None
                else None
            ),
        }

    except SQLGuardrailError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Query execution failed.",
        ) from exc
