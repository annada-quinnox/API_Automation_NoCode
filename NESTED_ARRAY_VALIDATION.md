# Nested Array Validation Test Cases

## Overview
Extended the API Test Case Generator to cover comprehensive validation testcases for nested Array fields, including arrays of objects, arrays of arrays, and arrays of primitives with various validation scenarios.

## Changes Made

### 1. **New Function: `generate_nested_array_tests()`**
   - **Location**: `testcaseengine.py` lines 647-751
   - **Purpose**: Generates specialized validation tests for nested array structures
   - **Features**:
     - Handles arrays of objects
     - Handles arrays of arrays
     - Handles arrays of primitives
     - Detects and tests field-specific validations within nested structures

### 2. **Enhanced Array Field Testing**
   - **Location**: `testcaseengine.py` lines 929-966
   - **New Validations Added**:
     - Non-array value type validation
     - Array size limit enforcement
     - Integration with nested array test generation

### 3. **Updated Payload Specific Tests**
   - **Location**: `testcaseengine.py` line 41-42
   - **Change**: Extended POST method to include payload-specific validation tests (previously only PUT/PATCH)
   - **Impact**: POST requests now generate comprehensive field and array validation tests

## Validation Scenarios Covered

### Array of Objects
When an array contains objects (e.g., `users: [{id: 1, email: 'john@example.com'}]`):

1. **Empty array validation**
   - ID: `POST_VAL_100`
   - Scenario: Empty array for field_name
   - Expected: 200 Success or 400 Empty array not allowed

2. **Null element validation**
   - ID: `POST_VAL_101`
   - Scenario: Null element in array field_name
   - Expected: 400 Array contains null elements

3. **Type validation**
   - ID: `POST_VAL_102`
   - Scenario: Non-array value for field_name
   - Expected: 400 Invalid data type - array expected

4. **Size limit validation**
   - ID: `POST_VAL_103`
   - Scenario: Array exceeds max length for field_name
   - Expected: 400 Array size exceeds maximum limit

5. **Missing required fields**
   - ID: `POST_NESTED_104`
   - Scenario: Array with object missing required fields
   - Expected: 400 Object in array missing required fields

6. **Extra fields validation**
   - ID: `POST_NESTED_105`
   - Scenario: Array with object having extra fields
   - Expected: 200 Success or 400 Unknown field in array object

7. **Invalid nested field types**
   - ID: `POST_NESTED_106`
   - Scenario: Array with invalid nested field types
   - Expected: 400 Invalid field type in nested array object

8. **Duplicate objects detection**
   - ID: `POST_NESTED_107`
   - Scenario: Array with duplicate objects
   - Expected: 200 Success or 400 Duplicate objects not allowed

9. **Nested field-specific validation** (e.g., invalid email in object)
   - ID: `POST_NESTED_108+`
   - Scenario: Array of objects with invalid [field_type] in nested field
   - Expected: 400 Invalid [field_type] in nested array object field

### Array of Arrays
When an array contains other arrays (e.g., `matrix: [[1, 2, 3], [4, 5, 6]]`):

1. **Standard array validations** (empty, null, type, size)
   - IDs: `POST_VAL_100 to POST_VAL_103`

2. **Nested array structure validation**
   - ID: `POST_NESTED_104`
   - Scenario: Array of arrays
   - Expected: 200 Success or 400 Nested arrays not allowed

3. **Null values in nested arrays**
   - ID: `POST_NESTED_105`
   - Scenario: Array of arrays with null
   - Expected: 400 Null values in nested array

### Array of Primitives
When an array contains primitive values (e.g., `ids: [1, 2, 3, 4, 5]`):

1. **Standard array validations** (empty, null, type, size)
   - IDs: `POST_VAL_100 to POST_VAL_103`

2. **Duplicate value detection**
   - ID: `POST_NESTED_104`
   - Scenario: Array with duplicate values
   - Expected: 200 Success or 400 Duplicate values not allowed

3. **Mixed type detection**
   - ID: `POST_NESTED_105`
   - Scenario: Array with mixed types
   - Expected: 400 Mixed types in array not allowed

4. **Type-specific validations** (e.g., for integer arrays)
   - ID: `POST_NESTED_106`
   - Scenario: Array of integers with string value
   - Expected: 400 Invalid type in numeric array

## Test Case Generation Examples

### Example 1: Array of User Objects
```json
{
  "users": [
    {
      "id": 1,
      "name": "John Doe",
      "email": "john@example.com"
    }
  ]
}
```

**Generated Nested Array Tests** (5 tests):
- Empty array validation
- Null element validation
- Type validation
- Size limit validation
- Missing required fields
- Extra fields in objects
- Invalid field types
- Duplicate objects
- Invalid email in nested field

### Example 2: Complex Nested Structure
```json
{
  "products": [
    {
      "id": "PROD001",
      "variants": [
        {
          "size": "M",
          "colors": ["red", "blue", "green"],
          "stock": 100
        }
      ]
    }
  ]
}
```

**Validation Coverage**:
- Product array validations
- Variant array validations
- Color array validations
- Type validations for nested integers
- Duplicate value detection in color arrays

## Benefits

1. **Comprehensive Coverage**: Automatically generates test cases for arrays at any nesting level
2. **Type Safety**: Validates both array structure and element types
3. **Edge Cases**: Covers empty arrays, null elements, duplicates, and size limits
4. **Field-Specific**: Applies appropriate validations based on detected field types (email, phone, date, etc.)
5. **Scalability**: Extends naturally to deeply nested structures

## Implementation Details

### Key Algorithm
1. Detect field type using `detect_field_type()` function
2. For array types, call `generate_nested_array_tests()`
3. Analyze first element of array to determine structure:
   - If object: Generate object-specific nested tests
   - If array: Generate array-of-arrays tests
   - If primitive: Generate primitive-array tests
4. For objects, iterate through keys to detect special field types (email, phone, etc.)
5. Generate appropriate validation scenarios for each detected case

### Functions Modified
- `_generate_payload_specific_tests()`: Now called for POST, PUT, and PATCH methods
- `generate_field_specific_tests()`: Enhanced to call nested array test generation
- New: `generate_nested_array_tests()`: Specialized handler for array validations

## Testing

All test cases were validated with:
- Array of objects with 5+ nested validation tests
- Array of arrays with 6+ nested validation tests
- Array of primitives with 7+ nested validation tests
- Complex multi-level structures with 26+ total validation tests

## Backward Compatibility

All changes are backward compatible:
- Existing test generation for non-array fields remains unchanged
- New nested array tests are additive (don't replace existing validations)
- API endpoints continue to work as before

## Example Test Output

```
Array of user objects:
  - POST_VAL_100: Empty array for users
  - POST_VAL_101: Null element in array users
  - POST_VAL_102: Non-array value for users
  - POST_VAL_103: Array exceeds max length for users
  - POST_NESTED_104: Array with object missing required fields - users
  - POST_NESTED_105: Array with object having extra fields - users
  - POST_NESTED_106: Array with invalid nested field types - users
  - POST_NESTED_107: Array with duplicate objects - users
  - POST_NESTED_108: Array of objects with invalid email in nested field email - users
```

Total tests generated for POST request: **27 test cases**
- 4 basic array validation tests
- 5+ nested array validation tests
- Remaining tests for other fields in the payload
