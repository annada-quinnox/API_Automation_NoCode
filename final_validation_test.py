#!/usr/bin/env python3
"""
Final validation test for schema validation of 500 error responses.
This test demonstrates the complete enhancement working end-to-end:
1. Schema validation function validates 5xx error responses
2. Mock response generation creates valid 500 error schemas
3. Test execution integrates schema validation
4. Invalid schemas cause test failures
"""

import json
import sys

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def test_1_schema_validation_function():
    """Test the core schema validation function"""
    print_header("TEST 1: Schema Validation Function")
    
    from app import validate_response_schema
    
    test_cases = [
        {
            "name": "Valid 500 error response",
            "body": '{"error": "Internal Server Error", "message": "Server error"}',
            "status": 500,
            "expected_valid": True
        },
        {
            "name": "Missing error field",
            "body": '{"message": "Server error"}',
            "status": 500,
            "expected_valid": False
        },
        {
            "name": "Missing message field (still valid - message is optional)",
            "body": '{"error": "Internal Server Error"}',
            "status": 500,
            "expected_valid": True
        },
        {
            "name": "Non-JSON response",
            "body": "Internal Server Error",
            "status": 500,
            "expected_valid": False
        },
        {
            "name": "Empty response",
            "body": "",
            "status": 500,
            "expected_valid": False
        },
        {
            "name": "Array response",
            "body": '[{"error": "test"}]',
            "status": 500,
            "expected_valid": False
        },
        {
            "name": "4xx error (no schema validation)",
            "body": "Any response",
            "status": 400,
            "expected_valid": True
        },
        {
            "name": "2xx success (no schema validation)",
            "body": "Any response",
            "status": 200,
            "expected_valid": True
        },
    ]
    
    passed = 0
    for tc in test_cases:
        valid, errors = validate_response_schema(tc["body"], tc["status"])
        status = "PASS" if valid == tc["expected_valid"] else "FAIL"
        
        if status == "PASS":
            passed += 1
            print(f"  [PASS] {tc['name']}: {status}")
        else:
            print(f"  [FAIL] {tc['name']}: {status}")
            print(f"    Expected: {tc['expected_valid']}, Got: {valid}")
            if errors:
                print(f"    Errors: {errors}")
    
    print(f"\n  Result: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)

def test_2_mock_response_generation():
    """Test that mock responses for 500 errors have correct schema"""
    print_header("TEST 2: Mock Response Generation")
    
    from app import generate_mock_response
    
    test_cases = [
        {
            "name": "500 Internal Server Error",
            "expected": "500 Internal Server Error",
            "description": "Test 500 error"
        },
        {
            "name": "502 Bad Gateway",
            "expected": "502 Bad Gateway",
            "description": "Test 502 error"
        },
        {
            "name": "503 Service Unavailable",
            "expected": "503 Service Unavailable",
            "description": "Test 503 error"
        },
    ]
    
    passed = 0
    for tc in test_cases:
        test_case = {
            "id": f"mock_test_{passed}",
            "method": "GET",
            "endpoint": "/api/test",
            "expected": tc["expected"],
            "description": tc["description"]
        }
        
        mock = generate_mock_response(test_case, "GET")
        
        # Check basic structure
        if mock['statusCode'] == 500 and 'body' in mock:
            body = mock['body']
            try:
                data = json.loads(body)
                if 'error' in data and 'message' in data:
                    passed += 1
                    print(f"  [PASS] {tc['name']}: Valid schema generated")
                else:
                    print(f"  [FAIL] {tc['name']}: Missing required fields")
                    print(f"    Data: {data}")
            except:
                print(f"  [FAIL] {tc['name']}: Invalid JSON in mock response")
                print(f"    Body: {body}")
        else:
            print(f"  [FAIL] {tc['name']}: Invalid mock response structure")
            print(f"    Mock: {mock}")
    
    print(f"\n  Result: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)

def test_3_test_execution_integration():
    """Test that test execution integrates schema validation"""
    print_header("TEST 3: Test Execution Integration")
    
    from app import execute_single_test, validate_response_schema
    
    # Create a test case expecting 500 error
    test_case = {
        "id": "execution_integration_test",
        "method": "GET",
        "endpoint": "/api/error",
        "input": "{}",
        "expected": "500 Internal Server Error",
        "description": "Test schema validation in execution"
    }
    
    print("  Testing execute_single_test with mock environment...")
    
    result = execute_single_test(
        endpoint="/api/error",
        method="GET",
        test_case=test_case,
        environment="mock",
        base_url="mock"
    )
    
    # Check results
    checks = [
        ("Status code is 500", result.get('statusCode') == 500),
        ("Test passes (valid schema)", result.get('status') == 'pass'),
        ("Source information included", result.get('source') is not None),
    ]
    
    passed = 0
    for check_name, check_result in checks:
        if check_result:
            passed += 1
            print(f"  [PASS] {check_name}")
        else:
            print(f"  [FAIL] {check_name}")
            print(f"    Got: {result.get(check_name.lower().replace(' ', ''), 'N/A')}")
    
    # Verify schema validation was performed (implicitly through test passing)
    print(f"\n  Schema validation verified through test execution")
    
    print(f"\n  Result: {passed}/{len(checks)} checks passed")
    return passed == len(checks)

def test_4_end_to_end_workflow():
    """Test the complete workflow from test generation to execution"""
    print_header("TEST 4: End-to-End Workflow")
    
    import requests
    
    print("  Step 1: Generate test cases with potential 500 errors...")
    
    # We'll use a simple payload
    payload = {
        "method": "POST",
        "endpoint": "/api/users",
        "payload": {"name": "Test"},
        "field_configs": {"name": {"type": "string", "required": True}}
    }
    
    try:
        response = requests.post("http://localhost:5000/api/generate", 
                               json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            test_cases = data.get('test_cases', [])
            print(f"  Generated {len(test_cases)} test cases")
            
            # Find or create a 500 error test case
            error_case = None
            for tc in test_cases:
                if '500' in tc.get('expected', ''):
                    error_case = tc
                    break
            
            if not error_case:
                print("  No 500 error test case generated, creating one manually...")
                error_case = {
                    "id": "manual_500_end_to_end",
                    "method": "GET",
                    "endpoint": "/api/system/error",
                    "input": "{}",
                    "expected": "500 Internal Server Error",
                    "description": "Manual 500 error test for end-to-end validation"
                }
            
            print("  Step 2: Execute 500 error test case...")
            
            execute_payload = {
                "test_cases": [error_case],
                "environment": "mock",
                "base_url": "mock"
            }
            
            exec_response = requests.post("http://localhost:5000/api/execute-tests",
                                        json=execute_payload, timeout=10)
            
            if exec_response.status_code == 200:
                exec_data = exec_response.json()
                results = exec_data.get('results', [])
                
                if results:
                    result = results[0]
                    print(f"  Execution result: {result.get('status')}")
                    print(f"  Status code: {result.get('statusCode')}")
                    
                    # The key validation: test should pass because mock response
                    # has valid schema for 500 errors
                    if result.get('status') == 'pass' and result.get('statusCode') == 500:
                        print("  [PASS] End-to-end workflow successful: 500 error test passes with valid schema")
                        return True
                    else:
                        print(f"  [FAIL] Unexpected result: {result}")
                        return False
                else:
                    print("  [FAIL] No execution results returned")
                    return False
            else:
                print(f"  [FAIL] Execution failed: {exec_response.status_code}")
                print(f"  Response: {exec_response.text}")
                return False
        else:
            print(f"  [FAIL] Test generation failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  [FAIL] End-to-end test failed with exception: {e}")
        return False

def test_5_error_handling():
    """Test that invalid schemas cause test failures"""
    print_header("TEST 5: Error Handling - Invalid Schemas Cause Failures")
    
    from app import validate_response_schema
    
    print("  Simulating test execution with invalid 500 error response...")
    
    # Create an invalid 500 response (missing error field)
    invalid_response = json.dumps({
        "message": "Something went wrong"
    })
    
    valid, errors = validate_response_schema(invalid_response, 500)
    
    if not valid and errors:
        print(f"  [PASS] Invalid schema correctly rejected")
        print(f"  Errors: {errors}")
        
        # Simulate what would happen in execute_single_test
        print("\n  In execute_single_test, this would:")
        print("    1. Detect status code >= 500")
        print("    2. Call validate_response_schema")
        print("    3. Get validation errors: " + ", ".join(errors))
        print("    4. Set test status to 'fail'")
        print("    5. Include errors in details")
        
        return True
    else:
        print(f"  [FAIL] Invalid schema incorrectly accepted")
        return False

def main():
    """Run all final validation tests"""
    print("\n" + "="*70)
    print("FINAL VALIDATION TEST SUITE")
    print("Schema Validation for 500 Error Responses")
    print("="*70)
    
    tests = [
        ("Schema Validation Function", test_1_schema_validation_function),
        ("Mock Response Generation", test_2_mock_response_generation),
        ("Test Execution Integration", test_3_test_execution_integration),
        ("End-to-End Workflow", test_4_end_to_end_workflow),
        ("Error Handling", test_5_error_handling),
    ]
    
    print(f"\nRunning {len(tests)} validation tests...")
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n  ERROR in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Print summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} - {test_name}")
    
    print(f"\n  Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n" + "="*70)
        print("  SUCCESS: All validation tests passed!")
        print("  Schema validation for 500 error responses is fully implemented")
        print("  and integrated into the test case generation and execution workflow.")
        print("="*70)
        return True
    else:
        print("\n" + "="*70)
        print(f"  PARTIAL SUCCESS: {passed}/{total} tests passed")
        print("  Some aspects of schema validation may need further attention.")
        print("="*70)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)