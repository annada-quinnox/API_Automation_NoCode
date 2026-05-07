#!/usr/bin/env python3
"""
Test schema validation for 500 error responses.
"""
import sys
sys.path.insert(0, '.')

from app import validate_response_schema, generate_mock_response, extract_response_code
import json

def test_validate_response_schema():
    print("Testing validate_response_schema...")
    
    # Valid 500 response
    body = json.dumps({"error": "Internal Server Error", "message": "Something went wrong"})
    valid, errors = validate_response_schema(body, 500)
    assert valid, f"Expected valid, got errors: {errors}"
    print("OK Valid 500 response passes")
    
    # Missing error field
    body = json.dumps({"message": "Something went wrong"})
    valid, errors = validate_response_schema(body, 500)
    assert not valid
    assert "Missing 'error' field" in errors[0]
    print("OK Missing error field detected")
    
    # Missing message field
    body = json.dumps({"error": "Internal Server Error"})
    valid, errors = validate_response_schema(body, 500)
    assert not valid
    assert "Missing 'message' field" in errors[0]
    print("OK Missing message field detected")
    
    # Non-object response
    body = json.dumps(["error", "message"])
    valid, errors = validate_response_schema(body, 500)
    assert not valid
    assert "Response body must be a JSON object" in errors[0]
    print("OK Non-object response detected")
    
    # Invalid types
    body = json.dumps({"error": 123, "message": "test"})
    valid, errors = validate_response_schema(body, 500)
    assert not valid
    assert "Field 'error' must be a string" in errors[0]
    print("OK Invalid error type detected")
    
    # 4xx error - optional validation (should pass)
    body = json.dumps({"error": "Bad Request", "message": "Invalid input"})
    valid, errors = validate_response_schema(body, 400)
    assert valid, f"4xx validation should pass but got errors: {errors}"
    print("OK 4xx error response passes")
    
    # 2xx success - no validation (should pass)
    body = json.dumps({"data": "anything"})
    valid, errors = validate_response_schema(body, 200)
    assert valid, f"2xx validation should pass but got errors: {errors}"
    print("OK 2xx success response passes")
    
    print("All schema validation tests passed.")

def test_mock_response_schema():
    print("\nTesting generate_mock_response for 500 error...")
    test_case = {
        "id": "TEST_500",
        "type": "Negative",
        "scenario": "Trigger 500 Internal Server Error",
        "expected": "500 Internal Server Error",
        "input": "GET /api/test"
    }
    mock = generate_mock_response(test_case, "GET")
    print(f"Mock response: {mock}")
    assert mock['statusCode'] == 500
    body = mock['body']
    # Validate schema
    valid, errors = validate_response_schema(body, 500)
    assert valid, f"Mock response fails schema validation: {errors}"
    print("OK Mock response passes schema validation")
    
    # Ensure the mock body matches expected structure
    data = json.loads(body)
    assert data['error'] == "Internal Server Error"
    assert data['message'] == "An unexpected error occurred on the server"
    print("OK Mock response content matches expected")

def test_extract_response_code():
    print("\nTesting extract_response_code for 500...")
    codes = extract_response_code("500 Internal Server Error")
    assert codes == ['500']
    print("OK Extracted 500 code")
    
    codes = extract_response_code("Some text 500 and 502")
    assert '500' in codes
    print("OK Extracted multiple codes")

if __name__ == "__main__":
    try:
        test_validate_response_schema()
        test_mock_response_schema()
        test_extract_response_code()
        print("\nAll tests passed successfully.")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)