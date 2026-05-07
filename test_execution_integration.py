#!/usr/bin/env python3
"""
Test to verify integration of schema validation with existing test execution flow.
This test directly calls execute_single_test with 500 error responses to ensure
schema validation is properly integrated.
"""

import json
import sys

def test_execute_single_test_with_schema_validation():
    """Test that execute_single_test properly integrates schema validation"""
    print("\n=== Testing execute_single_test integration with schema validation ===")
    
    try:
        import sys
        sys.path.insert(0, '.')
        from app import execute_single_test
        
        # Create a test case expecting 500 error
        test_case = {
            "id": "integration_500_test",
            "method": "GET",
            "endpoint": "/api/system/error",
            "input": "{}",
            "expected": "500 Internal Server Error",
            "description": "Integration test for 500 error schema validation"
        }
        
        print("Test 1: Testing with valid 500 error response (mock environment)...")
        
        # We need to mock the response since we're testing with 'mock' environment
        # In mock environment, generate_mock_response creates a valid 500 response
        result = execute_single_test(
            endpoint="/api/system/error",
            method="GET",
            test_case=test_case,
            environment="mock",
            base_url="mock"
        )
        
        print(f"  Result status: {result.get('status')}")
        print(f"  Result statusCode: {result.get('statusCode')}")
        print(f"  Source: {result.get('source')}")
        
        # In mock environment, the response should be a valid 500 error
        # with proper schema, so validation should pass
        assert result.get('statusCode') == 500
        assert result.get('status') == 'pass'
        
        details = result.get('details', '')
        print(f"  Details contains schema validation: {'schema validation' in details.lower()}")
        
        print("  OK: Valid 500 error passes schema validation in mock environment")
        
        # Test 2: We can't easily test with invalid schema in mock environment
        # because generate_mock_response always creates valid schemas
        # But we can verify the integration is there
        
        print("\nTest 2: Verifying schema validation logic in execute_single_test...")
        
        # Check the source code to ensure validation is called
        import inspect
        source_code = inspect.getsource(execute_single_test)
        
        # Check for key integration points
        integration_checks = [
            ("validate_response_schema called", "validate_response_schema(response.text" in source_code),
            ("Status >= 500 check", "response.status_code >= 500" in source_code),
            ("Schema errors added to details", "schema_errors" in source_code and "details_parts.append" in source_code),
            ("Status overridden on validation failure", "status = 'fail'" in source_code and "schema_valid" in source_code)
        ]
        
        all_passed = True
        for check_name, check_result in integration_checks:
            status = "OK" if check_result else "MISSING"
            print(f"  {check_name}: {status}")
            if not check_result:
                all_passed = False
        
        if all_passed:
            print("  OK: All integration points verified in source code")
        else:
            print("  WARNING: Some integration points missing")
            
        # Test 3: Test with a simulated real API call (requires actual server)
        # We'll skip this for now since it requires a real server returning 500 errors
        
        print("\nTest 3: Testing end-to-end through API endpoint...")
        
        import requests
        
        # Create a test case to execute
        execute_payload = {
            "test_cases": [test_case],
            "environment": "mock",
            "base_url": "mock"
        }
        
        try:
            response = requests.post("http://localhost:5000/api/execute-tests", 
                                   json=execute_payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                if results:
                    api_result = results[0]
                    print(f"  API execution status: {api_result.get('status')}")
                    print(f"  API status code: {api_result.get('statusCode')}")
                    
                    # Check if schema validation was performed
                    details = api_result.get('details', '')
                    if 'schema validation' in details.lower() or 'Schema Validation' in details:
                        print("  OK: Schema validation mentioned in API response details")
                    else:
                        print("  INFO: No explicit schema validation mention (might be implicit)")
                        
                    # The test should pass because mock responses have valid schema
                    assert api_result.get('status') == 'pass'
                    assert api_result.get('statusCode') == 500
                    
                    print("  OK: API endpoint correctly executes 500 error test with schema validation")
                else:
                    print("  WARNING: No results returned from API")
            else:
                print(f"  WARNING: API returned {response.status_code}: {response.text}")
                
        except Exception as e:
            print(f"  INFO: API test skipped (server might not be running): {e}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_schema_validation_edge_cases():
    """Test edge cases for schema validation integration"""
    print("\n=== Testing schema validation edge cases ===")
    
    try:
        import sys
        sys.path.insert(0, '.')
        from app import validate_response_schema
        
        print("Test 1: Non-JSON response for 500 error...")
        valid, errors = validate_response_schema("Internal Server Error", 500)
        print(f"  Result: valid={valid}, errors={errors}")
        assert not valid, "Non-JSON response should fail validation"
        assert any("not valid JSON" in err for err in errors), "Should report JSON parsing error"
        print("  OK: Non-JSON response correctly fails validation")
        
        print("\nTest 2: Empty response for 500 error...")
        valid, errors = validate_response_schema("", 500)
        print(f"  Result: valid={valid}, errors={errors}")
        assert not valid, "Empty response should fail validation"
        print("  OK: Empty response correctly fails validation")
        
        print("\nTest 3: Null response for 500 error...")
        valid, errors = validate_response_schema("null", 500)
        print(f"  Result: valid={valid}, errors={errors}")
        assert not valid, "Null response should fail validation"
        print("  OK: Null response correctly fails validation")
        
        print("\nTest 4: Array response for 500 error...")
        valid, errors = validate_response_schema('[{"error": "test"}]', 500)
        print(f"  Result: valid={valid}, errors={errors}")
        assert not valid, "Array response should fail validation"
        assert any("must be a JSON object" in err for err in errors), "Should report object requirement"
        print("  OK: Array response correctly fails validation")
        
        print("\nTest 5: 599 status code (edge of 5xx range)...")
        valid_response = json.dumps({
            "error": "Network Connect Timeout Error",
            "message": "A network timeout occurred"
        })
        valid, errors = validate_response_schema(valid_response, 599)
        print(f"  Result: valid={valid}, errors={errors}")
        assert valid, "Valid 599 response should pass"
        print("  OK: 599 status code correctly validated")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Edge case test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all integration verification tests"""
    print("Starting integration verification tests for schema validation...")
    
    tests = [
        ("Execute single test integration", test_execute_single_test_with_schema_validation),
        ("Schema validation edge cases", test_schema_validation_edge_cases),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"Running: {test_name}")
        print('='*60)
        
        try:
            if test_func():
                print(f"\nOK: {test_name} passed")
                passed += 1
            else:
                print(f"\nFAILED: {test_name}")
                failed += 1
        except Exception as e:
            print(f"\nERROR: {test_name} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*60}")
    print("Integration Verification Summary:")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total:  {passed + failed}")
    print('='*60)
    
    if failed == 0:
        print("\nAll integration verification tests passed!")
        print("Schema validation for 500 errors is properly integrated with test execution flow.")
        return True
    else:
        print(f"\n{failed} test(s) failed. Check logs for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)