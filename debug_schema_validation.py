#!/usr/bin/env python3
"""
Debug script to examine test case generation and schema validation for 500 error responses.
"""
import json
import sys
sys.path.insert(0, '.')

from testcaseengine import generate_testcases
from app import generate_mock_response, extract_response_code

def test_generation():
    """Generate test cases for a sample payload and inspect for 500 error schema validation."""
    generator = generate_testcases()
    
    # Sample data that might produce 500 error test cases?
    data = {
        "method": "POST",
        "endpoint": "/api/test",
        "payload": json.dumps({"name": "test", "age": 30}),
        "field_configs": {
            "name": {"type": "string", "required": True},
            "age": {"type": "integer", "required": False}
        },
        "baseUrl": "http://example.com"
    }
    
    test_cases = generator.generate_test_cases(data)
    print(f"Generated {len(test_cases)} test cases")
    
    # Look for test cases with expected 500 status
    found_500 = False
    for tc in test_cases:
        expected = tc.get('expected', '')
        if '500' in str(expected):
            found_500 = True
            print(f"Found 500 error test case: ID={tc.get('id')}, Scenario={tc.get('scenario')}")
            print(f"  Expected: {expected}")
            print(f"  Input: {tc.get('input')}")
            # Check if there's any schema validation field
            if 'schema' in tc:
                print(f"  Schema: {tc['schema']}")
            else:
                print("  No schema field present")
    
    if not found_500:
        print("No test cases with expected 500 status found in default generation.")
        # Let's see if we can trigger a 500 error test case by adding a scenario that triggers 500
        # Look at testcaseengine for negative test generation
        print("\nSearching for any test case that might be a 500 error...")
        for tc in test_cases:
            if 'internal server' in tc.get('scenario', '').lower() or 'server error' in tc.get('scenario', '').lower():
                print(f"Possible 500 scenario: {tc.get('scenario')}")
    
    # Examine generate_mock_response for 500 error
    print("\n--- Testing generate_mock_response for 500 error ---")
    # Create a test case with expected 500
    test_case_500 = {
        "id": "TEST_500",
        "type": "Negative",
        "scenario": "Trigger 500 Internal Server Error",
        "expected": "500 Internal Server Error",
        "input": "GET /api/test"
    }
    mock = generate_mock_response(test_case_500, "GET")
    print(f"Mock response for 500: {mock}")
    # Check if the mock response includes schema validation
    print(f"Mock body: {mock.get('body')}")
    
    # Check extract_response_code for 500
    codes = extract_response_code("500 Internal Server Error")
    print(f"Extracted codes: {codes}")
    
    # Now examine if there is any schema validation in the validation functions
    from app import validate_against_configs, validate_input_types
    print("\n--- Validation functions ---")
    print("validate_against_configs: validates request payload against field configs")
    print("validate_input_types: validates input types against original payload")
    print("No validation for response bodies.")
    
    # Let's see if there's any schema definition for 500 error responses in the codebase
    print("\n--- Searching for schema definitions ---")
    # Look for any JSON schema or response schema definitions
    import os
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'schema' in content and '500' in content:
                        print(f"Found 'schema' and '500' in {file}")
    
    # Check if there's a function that validates response schema
    print("\n--- Conclusion ---")
    print("Currently, the system generates mock responses for 500 errors with a fixed JSON structure:")
    print('  {"error": "Internal Server Error", "message": "An unexpected error occurred on the server"}')
    print("But there is no validation that actual API responses match this schema.")
    print("The enhancement likely requires adding schema validation for 500 error responses.")
    print("Possible approaches:")
    print("1. Add a response schema definition for 500 errors.")
    print("2. Integrate schema validation into test execution (execute_single_test).")
    print("3. Include schema validation in test case generation (add schema field).")

if __name__ == "__main__":
    test_generation()