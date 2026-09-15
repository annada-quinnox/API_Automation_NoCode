import time
import requests


def build_url(endpoint, base_url):
    base_url = (base_url or "").rstrip("/")
    endpoint = endpoint or "/"

    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    return base_url + endpoint


def run_etag_caching_test(
    base_url,
    endpoint,
    method,
    payload=None
):
    """
    Execute ETag / Cache-Control validation.

    Flow:
        1. Send the first request.
        2. Capture ETag and Cache-Control.
        3. If ETag exists, send a conditional request using
           If-None-Match.
        4. Expect HTTP 304 for the conditional request.
    """

    method = (method or "GET").upper()

    if method != "GET":
        return {
            "success": False,
            "metrics": {
                "requests_made": "0",
                "failures": "1",
                "median_ms": "0",
                "avg_ms": "0",
                "max_ms": "0",
                "rps": "0"
            },
            "sample_output": "",
            "failure_details": [
                "ETag caching test requires a GET request."
            ]
        }, 400

    url = build_url(endpoint, base_url)

    headers = {
        "Accept": "*/*",
        "User-Agent": "API-TestProbe/1.0"
    }

    requests_made = 0
    failures = 0
    latencies = []
    failure_details = []
    output = []

    # =========================================================
    # FIRST REQUEST
    # =========================================================

    try:
        start = time.time()

        first_response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        latency = (time.time() - start) * 1000

        requests_made += 1
        latencies.append(latency)

    except requests.RequestException as exc:

        return {
            "success": False,
            "metrics": {
                "requests_made": str(requests_made),
                "failures": "1",
                "median_ms": "0",
                "avg_ms": "0",
                "max_ms": "0",
                "rps": "0"
            },
            "sample_output": "",
            "failure_details": [
                f"First request failed: {str(exc)}"
            ]
        }, 502

    etag = first_response.headers.get("ETag")
    cache_control = first_response.headers.get("Cache-Control")

    output.append(
        f"First Request: HTTP {first_response.status_code}"
    )

    output.append(
        f"ETag: {etag or 'Not Present'}"
    )

    output.append(
        f"Cache-Control: "
        f"{cache_control or 'Not Present'}"
    )

    # =========================================================
    # BASIC CACHE HEADER CHECK
    # =========================================================

    if not etag and not cache_control:

        failures += 1

        failure_details.append(
            "Neither ETag nor Cache-Control header was present."
        )

        return {
            "success": True,
            "metrics": {
                "requests_made": str(requests_made),
                "failures": str(failures),
                "median_ms": str(round(latencies[0], 2)),
                "avg_ms": str(round(latencies[0], 2)),
                "max_ms": str(round(latencies[0], 2)),
                "rps": str(
                    round(
                        requests_made / (latencies[0] / 1000),
                        2
                    )
                )
            },
            "sample_output": "\n".join(output),
            "failure_details": failure_details
        }, 200

    # =========================================================
    # ETAG CONDITIONAL REQUEST
    # =========================================================

    if etag:

        conditional_headers = {
            "Accept": "*/*",
            "User-Agent": "API-TestProbe/1.0",
            "If-None-Match": etag
        }

        try:
            start = time.time()

            second_response = requests.get(
                url,
                headers=conditional_headers,
                timeout=10
            )

            latency = (time.time() - start) * 1000

            requests_made += 1
            latencies.append(latency)

            output.append(
                f"Conditional Request: "
                f"HTTP {second_response.status_code}"
            )

            output.append(
                f"If-None-Match: {etag}"
            )

            if second_response.status_code == 304:

                output.append(
                    "ETag validation: PASS"
                )

            else:

                failures += 1

                failure_details.append(
                    "Expected HTTP 304 Not Modified "
                    f"but received HTTP "
                    f"{second_response.status_code}."
                )

                output.append(
                    "ETag validation: FAIL"
                )

        except requests.RequestException as exc:

            failures += 1

            failure_details.append(
                f"Conditional request failed: {str(exc)}"
            )

    else:

        output.append(
            "ETag was not present; conditional "
            "If-None-Match validation was not performed."
        )

    # =========================================================
    # METRICS
    # =========================================================

    avg_latency = (
        sum(latencies) / len(latencies)
        if latencies
        else 0
    )

    sorted_latencies = sorted(latencies)

    if sorted_latencies:
        median_latency = sorted_latencies[
            len(sorted_latencies) // 2
        ]

        max_latency = max(sorted_latencies)

        elapsed_seconds = sum(latencies) / 1000

        rps = (
            requests_made / elapsed_seconds
            if elapsed_seconds > 0
            else 0
        )

    else:

        median_latency = 0
        max_latency = 0
        rps = 0

    return {
        "success": True,

        "metrics": {
            "requests_made": str(requests_made),
            "failures": str(failures),
            "median_ms": str(
                round(median_latency, 2)
            ),
            "avg_ms": str(
                round(avg_latency, 2)
            ),
            "max_ms": str(
                round(max_latency, 2)
            ),
            "rps": str(round(rps, 2))
        },

        "sample_output": "\n".join(output),

        "failure_details": failure_details
    }, 200