"""Run the Text-to-SQL benchmark against the configured database."""

import json
import math
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import execute_read_only
from app.main import app


BENCHMARK_FILE = PROJECT_ROOT / "evaluation" / "benchmark.json"
REPORT_FILE = PROJECT_ROOT / "evaluation" / "latest_results.json"



def values_match(expected, actual, *, rel_tol=1e-5, abs_tol=1e-4):
    """Compare numeric values with tolerance and other values exactly."""
    if expected is None or actual is None:
        return expected is actual

    if (
        isinstance(expected, (int, float))
        and not isinstance(expected, bool)
        and isinstance(actual, (int, float))
        and not isinstance(actual, bool)
    ):
        if not math.isfinite(float(expected)) or not math.isfinite(float(actual)):
            return expected == actual

        return math.isclose(
            float(expected),
            float(actual),
            rel_tol=rel_tol,
            abs_tol=abs_tol,
        )

    return type(expected) is type(actual) and expected == actual


def results_match(expected_rows, actual_rows):
    """Compare result values by column position, ignoring row order."""
    if len(expected_rows) != len(actual_rows):
        return False

    unmatched = list(actual_rows)

    for expected_row in expected_rows:
        expected_values = list(expected_row.values())
        matched_index = None

        for index, actual_row in enumerate(unmatched):
            actual_values = list(actual_row.values())

            if len(expected_values) != len(actual_values):
                continue

            if all(
                values_match(expected, actual)
                for expected, actual in zip(expected_values, actual_values)
            ):
                matched_index = index
                break

        if matched_index is None:
            return False

        unmatched.pop(matched_index)

    return not unmatched


def main():
    cases = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    results = []

    with TestClient(app) as client:
        for case in cases:
            record = {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "execution_success": False,
                "result_match": False,
                "recovery_attempted": False,
                "recovery_succeeded": False,
                "latency_ms": None,
                "error": None,
            }

            try:
                expected_columns, expected_rows = execute_read_only(
                    case["gold_sql"]
                )

                response = client.post(
                    "/v1/query",
                    json={"question": case["question"]},
                )

                if response.status_code != 200:
                    record["error"] = (
                        f"HTTP {response.status_code}: "
                        f"{response.json().get('detail', 'Unknown error')}"
                    )
                    results.append(record)
                    print(
                        f"[FAIL] {case['id']}: {record['error']}",
                        flush=True,
                    )
                    continue

                body = response.json()
                record["execution_success"] = True
                record["latency_ms"] = body.get("latency_ms")

                recovery = body.get("recovery") or {}
                record["recovery_attempted"] = recovery.get(
                    "attempted", False
                )
                record["recovery_succeeded"] = recovery.get(
                    "succeeded", False
                )


                actual_rows = body.get("rows", [])

                record["result_match"] = results_match(
                    expected_rows,
                    actual_rows,
                )

                record["expected_results"] = expected_rows
                record["actual_results"] = actual_rows

                record["generated_sql"] = body.get("sql")
                record["sanity_check"] = body.get("sanity_check")
                record["planning"] = body.get("planning")

                label = "PASS" if record["result_match"] else "MISMATCH"
                print(
                    f"[{label}] {case['id']} "
                    f"latency={record['latency_ms']}ms "
                    f"recovery={record['recovery_attempted']}",
                    flush=True,
                )

            except Exception as exc:
                # Store a concise diagnostic; do not stop the whole benchmark.
                record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                print(f"[ERROR] {case['id']}: {record['error']}", flush=True)

            results.append(record)

    total = len(results)
    executed = sum(item["execution_success"] for item in results)
    matched = sum(item["result_match"] for item in results)
    recovery_attempts = sum(item["recovery_attempted"] for item in results)
    recovery_successes = sum(item["recovery_succeeded"] for item in results)

    report = {
        "benchmark": str(BENCHMARK_FILE.relative_to(PROJECT_ROOT)),
        "total_cases": total,
        "execution_successes": executed,
        "result_matches": matched,
        "execution_accuracy": round(executed / total, 4) if total else 0,
        "result_accuracy": round(matched / total, 4) if total else 0,
        "recovery_attempts": recovery_attempts,
        "recovery_successes": recovery_successes,
        "cases": results,
    }

    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n---- Benchmark summary ----")
    print(f"Cases:               {total}")
    print(f"Executed:            {executed}/{total}")
    print(f"Reference matches:   {matched}/{total}")
    print(f"Execution accuracy:  {report['execution_accuracy']:.1%}")
    print(f"Result accuracy:     {report['result_accuracy']:.1%}")
    print(f"Recovery attempts:   {recovery_attempts}")
    print(f"Recovery successes:  {recovery_successes}")
    print(f"Report:              {REPORT_FILE}")

    # A mismatch is a valid benchmark outcome, not a runner crash.
    # Return a nonzero exit code only if no cases could execute.
    if total and executed == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
