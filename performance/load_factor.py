import json


def build_load_factor_script(
    base_url,
    endpoint,
    method,
    headers=None,
    payload=None,
    expected_codes=None
):
    """
    Build the Locust script used for Load Factor testing.
    """

    headers = headers or {}
    payload = payload or {}
    expected_codes = expected_codes or []

    safe_headers = json.dumps(headers)
    safe_payload = json.dumps(payload)
    safe_expected_codes = json.dumps(expected_codes)

    return f"""from locust import HttpUser, task, between


class APIUser(HttpUser):

    wait_time = between(0.01, 0.05)

    host = {json.dumps(base_url)}

    @task
    def execute_load_factor_request(self):

        headers = {safe_headers}

        payload_data = {safe_payload}

        expected_codes = [
            str(code)
            for code in {safe_expected_codes}
            if str(code).upper() != "N/A"
        ]

        kwargs = {{
            "headers": headers,
            "catch_response": True,
            "timeout": 15.0,
        }}

        if {json.dumps(method.upper())} in ["GET", "DELETE"]:

            if isinstance(payload_data, dict) and payload_data:
                kwargs["params"] = payload_data

        else:

            if isinstance(payload_data, dict) and payload_data:
                kwargs["json"] = payload_data

            elif payload_data:
                kwargs["data"] = payload_data

        with self.client.request(
            {json.dumps(method.upper())},
            {json.dumps(endpoint)},
            **kwargs
        ) as response:

            if not expected_codes:

                if response.status_code < 400:
                    response.success()
                else:
                    response.failure(
                        f"HTTP {{response.status_code}}"
                    )

            elif str(response.status_code) in expected_codes:

                response.success()

            else:

                response.failure(
                    f"Expected HTTP {{expected_codes}}, "
                    f"got HTTP {{response.status_code}}: "
                    f"{{response.text[:100]}}"
                )
"""