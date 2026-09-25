import json


def build_load_factor_script(
    base_url,
    endpoint,
    method,
    headers=None,
    payload=None,
    expected_codes=None,
    status_policy="default",
    status_metrics_file="",
):
    """
    Build the Locust script used for configurable performance execution.

    The caller is expected to pass the already-validated configuration.
    This builder does not invent users, spawn rate, duration, or payload
    values. The runner supplies those values through the Locust command.
    """

    headers = headers or {}
    payload = payload if payload is not None else {}
    expected_codes = expected_codes or []

    safe_headers = json.dumps(headers, ensure_ascii=False, default=str)
    safe_payload = json.dumps(payload, ensure_ascii=False, default=str)
    safe_expected_codes = json.dumps(expected_codes)
    safe_status_policy = json.dumps(status_policy)
    safe_status_metrics_file = json.dumps(status_metrics_file)

    method_upper = str(method or "GET").upper()

    return f"""from locust import HttpUser, task, constant, events
import json


STATUS_COUNTS = {{
    "2xx": 0,
    "3xx": 0,
    "4xx": 0,
    "5xx": 0,
    "429": 0,
}}


@events.request.add_listener
def record_status_code(
    request_type,
    name,
    response_time,
    response_length,
    response,
    context,
    exception,
    start_time=None,
    url=None,
    **kwargs
):
    if response is None:
        return

    try:
        status_code = int(response.status_code)
    except (TypeError, ValueError, AttributeError):
        return

    if status_code == 429:
        STATUS_COUNTS["429"] += 1
    elif 200 <= status_code < 300:
        STATUS_COUNTS["2xx"] += 1
    elif 300 <= status_code < 400:
        STATUS_COUNTS["3xx"] += 1
    elif 400 <= status_code < 500:
        STATUS_COUNTS["4xx"] += 1
    elif status_code >= 500:
        STATUS_COUNTS["5xx"] += 1


@events.test_stop.add_listener
def write_status_counts(environment, **kwargs):
    metrics_file = {safe_status_metrics_file}

    if not metrics_file:
        return

    try:
        with open(metrics_file, "w", encoding="utf-8") as file:
            json.dump(STATUS_COUNTS, file)
    except OSError:
        pass


class APIUser(HttpUser):

    # No hidden wait interval is added. Request pacing is controlled by
    # the Locust users/spawn-rate configuration supplied by the backend.
    wait_time = constant(0)

    host = {json.dumps(base_url, ensure_ascii=False)}

    @task
    def execute_configured_request(self):

        headers = {safe_headers}
        payload_data = {safe_payload}
        expected_codes = [
            str(code)
            for code in {safe_expected_codes}
            if str(code).upper() != "N/A"
        ]
        status_policy = {safe_status_policy}

        kwargs = {{
            "headers": headers,
            "catch_response": True,
            "timeout": 15.0,
        }}

        if {json.dumps(method_upper)} in ["GET", "DELETE"]:
            if isinstance(payload_data, dict) and payload_data:
                kwargs["params"] = payload_data

        else:
            if isinstance(payload_data, (dict, list)):
                if payload_data:
                    kwargs["json"] = payload_data
            elif payload_data is not None and payload_data != "":
                kwargs["data"] = payload_data

        with self.client.request(
            {json.dumps(method_upper)},
            {json.dumps(endpoint, ensure_ascii=False)},
            **kwargs
        ) as response:

            if status_policy == "rate_limit":
                # A rate-limit test treats normal responses and HTTP 429 as
                # observable outcomes. Other 4xx/5xx responses are failures.
                if 200 <= response.status_code < 400 or response.status_code == 429:
                    response.success()
                else:
                    response.failure(
                        f"Unexpected HTTP {{response.status_code}}"
                    )

            elif expected_codes:
                if str(response.status_code) in expected_codes:
                    response.success()
                else:
                    response.failure(
                        f"Expected HTTP {{expected_codes}}, "
                        f"got HTTP {{response.status_code}}: "
                        f"{{response.text[:100]}}"
                    )

            else:
                if response.status_code < 400:
                    response.success()
                else:
                    response.failure(
                        f"HTTP {{response.status_code}}"
                    )
"""