import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from performance.caching import run_etag_caching_test
from performance.load_factor import build_load_factor_script
import requests


class PerformanceExecutionError(Exception):
    """Raised when performance execution fails."""


def parse_query_params(input_data):
    if not isinstance(input_data, str):
        return input_data if isinstance(input_data, dict) else {}

    qs = input_data.strip()

    if qs.startswith('?'):
        qs = qs[1:]

    if ' ' in qs:
        parts = qs.split(' ')
        for part in parts:
            if '?' in part:
                qs = part.split('?')[1]
                break
            elif '=' in part:
                qs = part
                break

    elif '?' in qs:
        qs = qs.split('?')[1]

    params = {}

    if not qs or '=' not in qs:
        return params

    for pair in qs.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)

            if value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif value.isdigit():
                value = int(value)
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass

            params[key] = value

    return params


def extract_response_code(expected_input):
    if not expected_input:
        return ["N/A"]

    if isinstance(expected_input, list):
        valid_codes = []

        for item in expected_input:
            if item is None:
                continue

            item_str = str(item).strip()

            if re.match(r'^[1-5]\d{2}$', item_str):
                valid_codes.append(item_str)

            elif item_str.upper() != "N/A":
                matches = re.findall(r'\b([1-5]\d{2})\b', item_str)
                valid_codes.extend(matches)

        return valid_codes if valid_codes else ["N/A"]

    expected_str = str(expected_input)
    expected_lower = expected_str.lower()

    if 'default sort' in expected_lower or 'fallback' in expected_lower:
        codes = re.findall(r'\b([1-5]\d{2})\b', expected_str)

        normalized = []

        for code in codes:
            if code not in normalized:
                normalized.append(code)

        if '200' not in normalized:
            normalized.append('200')

        if normalized:
            return normalized

    matches = re.findall(r'\b([1-5]\d{2})\b', expected_str)

    if matches:
        return matches

    if 'created' in expected_lower:
        return ["201"]

    if 'no content' in expected_lower:
        return ["204"]

    if 'success' in expected_lower or 'ok' in expected_lower:
        return ["200"]

    if (
        'bad request' in expected_lower
        or 'invalid' in expected_lower
        or 'missing' in expected_lower
    ):
        return ["400"]

    if 'unauthorized' in expected_lower:
        return ["401"]

    if 'forbidden' in expected_lower:
        return ["403"]

    if 'not found' in expected_lower:
        return ["404"]

    if 'conflict' in expected_lower:
        return ["409"]

    if (
        'too many' in expected_lower
        or 'rate limit' in expected_lower
    ):
        return ["429"]

    return ["N/A"]

PERCENTILE_THRESHOLDS = {
    "p50": 500,
    "p95": 1000,
    "p99": 2000,
}


def _parse_percentile(value):
    """
    Convert a Locust percentile CSV value to milliseconds.
    Returns None when the value cannot be evaluated.
    """
    if value is None:
        return None

    text = str(value).strip().replace(",", "")

    if not text or text.upper() in {"N/A", "NA", "NONE"}:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _build_locust_metrics(row):
    """
    Build the Locust metrics returned to the frontend,
    including P50/P95/P99 SLA evaluation.
    """

    p50 = _parse_percentile(row.get("50%"))
    p95 = _parse_percentile(row.get("95%"))
    p99 = _parse_percentile(row.get("99%"))

    p50_pass = (
        p50 is not None
        and p50 < PERCENTILE_THRESHOLDS["p50"]
    )

    p95_pass = (
        p95 is not None
        and p95 < PERCENTILE_THRESHOLDS["p95"]
    )

    p99_pass = (
        p99 is not None
        and p99 < PERCENTILE_THRESHOLDS["p99"]
    )

    return {
        "requests_made": row.get(
            "Request Count",
            "0"
        ),

        "failures": row.get(
            "Failure Count",
            "0"
        ),

        "median_ms": row.get(
            "Median Response Time",
            "0"
        ),

        "avg_ms": row.get(
            "Average Response Time",
            "0"
        ),

        "max_ms": row.get(
            "Max Response Time",
            "0"
        ),

        "rps": row.get(
            "Requests/s",
            "0"
        ),

        "p50_ms": (
            p50 if p50 is not None
            else "N/A"
        ),

        "p95_ms": (
            p95 if p95 is not None
            else "N/A"
        ),

        "p99_ms": (
            p99 if p99 is not None
            else "N/A"
        ),

        "p50_pass": p50_pass,
        "p95_pass": p95_pass,
        "p99_pass": p99_pass,

        "percentile_passed": (
            p50_pass
            and p95_pass
            and p99_pass
        )
    }

def build_url(endpoint, base_url):
    base_url = (base_url or "").rstrip("/")
    endpoint = endpoint or "/"

    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    return base_url + endpoint


PERFORMANCE_TYPES = {
    "load_factor",
    "stress_factor",
    "endurance",
    "rate_limit",
    "caching",
}


OBSERVATIONAL_EXPECTATION_KEYWORDS = (
    "capture",
    "monitor",
    "stable",
    "within sla",
    "error rate",
    "throughput",
    "response time",
    "latency",
    "breaking point",
    "degradation",
    "recovery time",
    "performance should",
    "return toward",
    "large payload",
    "large response",
    "simultaneous",
    "race-condition",
    "deadlock",
    "no continuous",
    "below threshold",
    "above threshold",
)


def replace_path_parameters(endpoint, path_parameter_values=None):
    """
    Resolve every {placeholder} using the testcase's configured path values.

    Performance execution must never send an unresolved placeholder to the
    target API. A missing value is reported by the caller instead.
    """

    values = path_parameter_values or {}

    def replace_match(match):
        name = match.group(1).strip()
        value = values.get(name)

        if value is None and name in values:
            value = values[name]

        if value is None:
            return match.group(0)

        return str(value)

    return re.sub(r"\{([^{}]+)\}", replace_match, str(endpoint or "/"))


def _find_unresolved_path_parameters(endpoint):
    return re.findall(r"\{([^{}]+)\}", str(endpoint or ""))


def _is_missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _normalize_performance_configuration(performance_config):
    """
    Validate and normalize the Test Plan configuration.

    No execution value is defaulted here. Users, spawn rate, duration, unit,
    and caching choice must originate from the configuration sent by the UI.
    """

    if not isinstance(performance_config, dict):
        return None, "Performance configuration is required."

    performance_type = str(performance_config.get("type", "")).strip().lower()

    if performance_type not in PERFORMANCE_TYPES:
        return None, (
            "Invalid performance configuration type. "
            f"Expected one of: {', '.join(sorted(PERFORMANCE_TYPES))}."
        )

    if performance_type == "caching":
        value = performance_config.get("value")

        if _is_missing(value):
            return None, "Caching configuration value is required."

        normalized_value = str(value).strip().lower()
        if normalized_value not in {"yes", "no"}:
            return None, "Caching configuration must be exactly Yes or No."

        return {
            "type": "caching",
            "value": "Yes" if normalized_value == "yes" else "No",
        }, None

    users_raw = performance_config.get("value")
    spawn_rate_raw = performance_config.get("spawnRate")
    if spawn_rate_raw is None:
        spawn_rate_raw = performance_config.get("spawn")
    duration_raw = performance_config.get("duration")
    unit_raw = performance_config.get("unit")

    missing_fields = []

    if _is_missing(users_raw):
        missing_fields.append("Users")

    if _is_missing(spawn_rate_raw):
        missing_fields.append("Spawn Rate")

    if _is_missing(duration_raw):
        missing_fields.append("Duration")

    if _is_missing(unit_raw):
        missing_fields.append("Unit")

    if missing_fields:
        return None, (
            "Performance configuration is incomplete. Missing: "
            + ", ".join(missing_fields)
            + "."
        )

    try:
        users = int(users_raw)
    except (TypeError, ValueError):
        return None, "Users must be a positive integer."

    try:
        spawn_rate = float(spawn_rate_raw)
    except (TypeError, ValueError):
        return None, "Spawn Rate must be a positive number."

    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        return None, "Duration must be a positive number."

    if users <= 0:
        return None, "Users must be greater than 0."

    if spawn_rate <= 0:
        return None, "Spawn Rate must be greater than 0."

    if duration <= 0:
        return None, "Duration must be greater than 0."

    unit = str(unit_raw).strip().lower()

    if unit not in {"seconds", "minutes", "hours"}:
        return None, "Unit must be seconds, minutes, or hours."

    if duration.is_integer():
        duration_text = str(int(duration))
    else:
        duration_text = str(duration)

    unit_suffix = {
        "seconds": "s",
        "minutes": "m",
        "hours": "h",
    }[unit]

    return {
        "type": performance_type,
        "users": users,
        "spawn_rate": spawn_rate,
        "duration": duration,
        "duration_text": duration_text,
        "unit": unit,
        "run_time": f"{duration_text}{unit_suffix}",
    }, None


def _is_observational_performance_expectation(expected):
    text = str(expected or "").strip().lower()

    if not text:
        return True

    return any(keyword in text for keyword in OBSERVATIONAL_EXPECTATION_KEYWORDS)


def _prepare_performance_payload(test_case):
    """
    Determine the actual request payload without treating the performance
    scenario's descriptive input text as a request body.

    A future caller can explicitly provide request_input/payload on the
    testcase. Otherwise, JSON-like input is retained; plain descriptive
    performance text becomes an empty request payload.
    """

    explicit_payload = test_case.get("request_input")
    if explicit_payload is None:
        explicit_payload = test_case.get("payload")

    if explicit_payload is not None:
        return explicit_payload

    input_value = test_case.get("input", {})

    if isinstance(input_value, (dict, list)) or input_value is None:
        return input_value if input_value is not None else {}

    if isinstance(input_value, str):
        stripped = input_value.strip()

        if not stripped:
            return {}

        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except (TypeError, ValueError):
                pass

        # Matrix performance test cases use input as human-readable
        # configuration text. It must never be sent as the API request body.
        return {}

    return input_value


def _build_status_policy(performance_type, expected):
    """
    Select response classification without using performance configuration
    text to choose the execution mode.
    """

    if performance_type == "rate_limit":
        return "rate_limit"

    if _is_observational_performance_expectation(expected):
        return "default"

    return "explicit"


def _read_status_metrics(status_metrics_file):
    default = {
        "2xx": 0,
        "3xx": 0,
        "4xx": 0,
        "5xx": 0,
        "429": 0,
    }

    if not status_metrics_file or not os.path.exists(status_metrics_file):
        return default

    try:
        with open(status_metrics_file, "r", encoding="utf-8") as file:
            data = json.load(file)

        for key in default:
            try:
                default[key] = int(data.get(key, 0) or 0)
            except (TypeError, ValueError):
                default[key] = 0

        return default
    except (OSError, ValueError, TypeError):
        return default


def _read_locust_failure_details(csv_file_failures):
    failure_details = []

    if not os.path.exists(csv_file_failures):
        return failure_details

    try:
        with open(
            csv_file_failures,
            mode="r",
            encoding="utf-8"
        ) as file:
            reader = csv.DictReader(file)

            for row in reader:
                err_msg = row.get("Error", "")
                occ = row.get("Occurrences", "")

                if err_msg:
                    failure_details.append(
                        f"{err_msg} (Occurred {occ} times)"
                    )
    except OSError as exc:
        failure_details.append(
            f"Failed to read Locust failure report: {str(exc)}"
        )

    return failure_details


def _read_locust_metrics(csv_file_stats):
    if not os.path.exists(csv_file_stats):
        return {}

    with open(
        csv_file_stats,
        mode="r",
        encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("Name") == "Aggregated":
                return _build_locust_metrics(row)

        file.seek(0)
        reader = csv.DictReader(file)

        for row in reader:
            return _build_locust_metrics(row)

    return {}


def _cleanup_performance_files(locust_file, csv_prefix, status_metrics_file):
    for filename in [
        locust_file,
        status_metrics_file,
        f"{csv_prefix}_stats.csv",
        f"{csv_prefix}_stats_history.csv",
        f"{csv_prefix}_failures.csv",
        f"{csv_prefix}_exceptions.csv",
    ]:
        if not filename:
            continue

        try:
            os.remove(filename)
        except OSError:
            pass


def run_performance_test(data):
    """
    Execute a performance testcase using only the supplied Test Plan
    performance configuration.

    Configuration contract:
      - caching: value (Yes/No)
      - load_factor/stress_factor/endurance/rate_limit:
        value, spawnRate/spawn, duration, unit

    The runner never reads the descriptive matrix input to derive users,
    spawn rate, duration, or execution type.
    """

    data = data if isinstance(data, dict) else {}

    test_case = data.get("testCase")
    if not isinstance(test_case, dict):
        test_case = {}

    normalized_config, config_error = _normalize_performance_configuration(
        data.get("performanceConfig")
    )

    if config_error:
        return {
            "success": False,
            "error": config_error,
        }, 400

    performance_type = normalized_config["type"]

    base_url = (
        test_case.get("baseUrl")
        or test_case.get("base_url")
        or data.get("baseUrl")
        or data.get("base_url")
        or ""
    )

    base_url = str(base_url).strip()

    if not base_url or base_url.lower() in {"mock", "custom", "n/a", "no-base-url"}:
        return {
            "success": False,
            "error": "Performance testing requires a real Base URL, not a mock/custom environment.",
        }, 400

    method = str(
        test_case.get("method")
        or data.get("method")
        or "GET"
    ).strip().upper()

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return {
            "success": False,
            "error": f"Unsupported HTTP method for performance execution: {method}",
        }, 400

    expected = test_case.get("expected", "N/A")
    if expected == "N/A" or not expected:
        expected = test_case.get("expected_status", "N/A")

    current_endpoint = (
        test_case.get("endpoint")
        or data.get("endpoint")
        or "/"
    )

    path_parameter_values = test_case.get("path_parameter_values") or {}
    current_endpoint = replace_path_parameters(
        current_endpoint,
        path_parameter_values
    )

    unresolved = _find_unresolved_path_parameters(current_endpoint)
    if unresolved:
        return {
            "success": False,
            "error": (
                "Performance execution cannot start because the endpoint "
                "contains unresolved path parameter(s): "
                + ", ".join(unresolved)
            ),
        }, 400

    payload = _prepare_performance_payload(test_case)

    if performance_type == "caching":
        caching_enabled = normalized_config["value"].strip().lower()

        if caching_enabled != "yes":
            return {
                "success": True,
                "metrics": {
                    "requests_made": "0",
                    "failures": "0",
                    "median_ms": "0",
                    "avg_ms": "0",
                    "max_ms": "0",
                    "rps": "0",
                },
                "sample_output": (
                    "Caching test skipped because "
                    "Caching configuration is set to No."
                ),
                "failure_details": [],
                "configuration": normalized_config,
            }, 200

        result, status_code = run_etag_caching_test(
            base_url=base_url,
            endpoint=current_endpoint,
            method=method,
            payload=payload,
        )

        if isinstance(result, dict):
            result["configuration"] = normalized_config

        return result, status_code

    expected_codes = extract_response_code(expected)
    status_policy = _build_status_policy(performance_type, expected)
    builder_expected_codes = expected_codes if status_policy == "explicit" else []

    timestamp = int(time.time() * 1000)
    csv_prefix = f"perf_results_{timestamp}"
    locust_file = f"dynamic_locustfile_{timestamp}.py"
    status_metrics_file = os.path.abspath(
        f"{csv_prefix}_status_codes.json"
    )

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    locust_script = build_load_factor_script(
        base_url=base_url,
        endpoint=current_endpoint,
        method=method,
        headers=headers,
        payload=payload,
        expected_codes=builder_expected_codes,
        status_policy=status_policy,
        status_metrics_file=status_metrics_file,
    )

    with open(
        locust_file,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(locust_script)

    users = normalized_config["users"]
    spawn_rate = normalized_config["spawn_rate"]
    run_time = normalized_config["run_time"]

    print(
        "\n🚀 Starting Locust Performance Test on "
        f"{base_url}{current_endpoint} [{method}]..."
    )
    print("\n" + "=" * 70)
    print("LOCUST TARGET DEBUG")
    print("=" * 70)
    print("Base URL :", base_url)
    print("Endpoint :", current_endpoint)
    print("Full URL :", build_url(current_endpoint, base_url))
    print("Method   :", method)
    print("Perf Type:", performance_type)
    print("Users    :", users)
    print("Spawn    :", spawn_rate)
    print("Duration :", normalized_config["duration"], normalized_config["unit"])
    print("Run Time :", run_time)
    print("Status   :", status_policy)
    print("=" * 70)

    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        locust_file,
        "--headless",
        "-u",
        str(users),
        "-r",
        str(spawn_rate),
        "--run-time",
        run_time,
        "--csv",
        csv_prefix,
    ]

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        print("\n--- LOCUST STDOUT ---")
        print(process.stdout)

        print("\n--- LOCUST STDERR ---")
        print(process.stderr)

        print("LOCUST EXIT CODE:", process.returncode)

        csv_file_stats = f"{csv_prefix}_stats.csv"
        csv_file_failures = f"{csv_prefix}_failures.csv"

        failure_details = _read_locust_failure_details(csv_file_failures)
        metrics = _read_locust_metrics(csv_file_stats)
        status_counts = _read_status_metrics(status_metrics_file)

        if not metrics:
            stdout_tail = (process.stdout or "").strip()[-2000:]
            stderr_tail = (process.stderr or "").strip()[-2000:]

            detail_parts = [
                "Locust failed to generate CSV results."
            ]

            if process.returncode:
                detail_parts.append(
                    f"Locust exit code: {process.returncode}."
                )

            if stderr_tail:
                detail_parts.append(
                    f"STDERR: {stderr_tail}"
                )
            elif stdout_tail:
                detail_parts.append(
                    f"STDOUT: {stdout_tail}"
                )

            return {
                "success": False,
                "error": " ".join(detail_parts),
            }, 500

        metrics.update({
            "status_2xx": status_counts["2xx"],
            "status_3xx": status_counts["3xx"],
            "status_4xx": status_counts["4xx"],
            "status_5xx": status_counts["5xx"],
            "status_429": status_counts["429"],
        })

        return {
            "success": True,
            "metrics": metrics,
            "sample_output": (
                "Performance execution completed by Locust using the "
                "configured users, spawn rate, and duration."
            ),
            "failure_details": failure_details,
            "configuration": normalized_config,
        }, 200

    except FileNotFoundError:
        return {
            "success": False,
            "error": (
                "Locust is not available on the server PATH. "
                "Install the configured Locust dependency and try again."
            ),
        }, 500

    except Exception as exc:
        return {
            "success": False,
            "error": f"Performance execution failed: {str(exc)}",
        }, 500

    finally:
        _cleanup_performance_files(
            locust_file,
            csv_prefix,
            status_metrics_file,
        )
