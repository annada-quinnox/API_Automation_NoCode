from flask import Flask, render_template, request, jsonify, send_file
# import os  # Unused import
# from werkzeug.utils import secure_filename  # Unused import
from flask_cors import CORS
from testcaseengine import generate_testcases
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from io import BytesIO
import json
import re
import requests
# from urllib.parse import urljoin  # Unused import - custom build_url() used instead
from datetime import datetime
from database import get_database, initialize_database

def flatten(data, parent_key="", sep="."):
    items = {}
    if isinstance(data, dict):
        for k, v in data.items():
            # Ensure key is a string to avoid concatenation errors
            str_k = str(k)
            new_key = parent_key + sep + str_k if parent_key else str_k
            if isinstance(v, dict):
                items.update(flatten(v, new_key, sep=sep))
            elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                items.update(flatten(v[0], new_key, sep=sep))
            else:
                items[new_key] = v
    return items

def get_data_type(value):
    if value is None: return 'null'
    if isinstance(value, bool): return 'boolean'
    # Check boolean before integer because bool is a subclass of int in Python
    if isinstance(value, int): return 'integer'
    if isinstance(value, float): return 'number'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    return 'string'

def parse_query_params(input_data):
    if not isinstance(input_data, str):
        return input_data if isinstance(input_data, dict) else {}
    
    # Remove leading '?' if present
    qs = input_data.strip()
    if qs.startswith('?'):
        qs = qs[1:]
    
    # If it's a full URL or "METHOD URL", extract the query string part
    if ' ' in qs: # "GET /api/test?a=b"
        parts = qs.split(' ')
        for part in parts:
            if '?' in part:
                qs = part.split('?')[1]
                break
            elif '=' in part:
                qs = part
                break
    elif '?' in qs: # "/api/test?a=b"
        qs = qs.split('?')[1]
        
    params = {}
    if not qs or '=' not in qs:
        return params

    for pair in qs.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            # Try to convert to int/float/bool if it looks like one
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

def validate_against_configs(input_data, field_configs, source='body'):
    if not input_data or not field_configs:
        return True, []
    
    try:
        if isinstance(input_data, str):
            try:
                input_json = json.loads(input_data)
            except:
                # If it's not JSON, it might be a query string if source is 'query'
                if source == 'query':
                    input_json = parse_query_params(input_data)
                else:
                    return False, [f"Invalid JSON payload: {input_data}"]
        else:
            input_json = input_data
    except Exception as e:
        return False, [f"Validation error: {str(e)}"]

    if not isinstance(input_json, dict):
        return True, []

    flat_input = flatten(input_json)
    errors = []
    
    for field, config in field_configs.items():
        expected_type = config.get('type')
        is_required = config.get('required', False)
        
        if field not in flat_input:
            if is_required:
                errors.append(f"For '{source}' at path '{field}': Missing required field.")
            continue
            
        value = flat_input[field]
        if value is None:
            if is_required:
                errors.append(f"For '{source}' at path '{field}': Value cannot be null.")
            continue
            
        curr_type = get_data_type(value)
        
        # STRICT Type Check
        type_mismatch = False
        
        # Mapping frontend type names to our get_data_type names
        check_type = expected_type
        if expected_type in ['email', 'uuid', 'date', 'datetime', 'url', 'password', 'phone']:
            check_type = 'string'
        
        # Standard Python types to check
        if check_type == 'string' and not isinstance(value, str):
            type_mismatch = True
        elif check_type == 'integer' and (not isinstance(value, int) or isinstance(value, bool)):
            type_mismatch = True
        elif check_type == 'number' and not isinstance(value, (int, float)):
            type_mismatch = True
        elif check_type == 'boolean' and not isinstance(value, bool):
            type_mismatch = True
        elif check_type == 'array' and not isinstance(value, list):
            type_mismatch = True
        elif check_type == 'object' and not isinstance(value, dict):
            type_mismatch = True

        if type_mismatch:
            errors.append(f"For '{source}' at path '{field}': Value must be a {expected_type}.")
    
    if errors:
        return False, errors
    return True, []

def validate_input_types(input_data, original_payload):
    if not input_data or not original_payload:
        return True, []
    
    try:
        if isinstance(input_data, str):
            input_json = json.loads(input_data)
        else:
            input_json = input_data
            
        if isinstance(original_payload, str):
            original_json = json.loads(original_payload)
        else:
            original_json = original_payload
    except:
        return True, []

    if not isinstance(input_json, dict) or not isinstance(original_json, dict):
        return True, []

    flat_input = flatten(input_json)
    flat_orig = flatten(original_json)
    errors = []
    
    for key, value in flat_input.items():
        if key in flat_orig and value is not None:
            orig_val = flat_orig[key]
            if orig_val is not None:
                orig_type = get_data_type(orig_val)
                curr_type = get_data_type(value)
                
                # Special numeric handling
                if orig_type == 'integer' and curr_type == 'number':
                    errors.append(f"For 'body' at path '{key}': Expected integer, but sent float/number.")
                elif orig_type != curr_type:
                    errors.append(f"For 'body' at path '{key}': Expected {orig_type}, but sent {curr_type}.")
    
    if errors:
        return False, errors
    return True, []

def validate_response_schema(response_body, status_code):
    """
    Validate that a response body matches the expected schema for the given status code.
    Returns (is_valid, errors_list).
    """
    if not response_body:
        # Empty response for 5xx errors is invalid
        if status_code >= 500:
            return False, ["Empty response body for 5xx error"]
        return True, []
    
    # Parse JSON if possible
    try:
        if isinstance(response_body, str):
            data = json.loads(response_body)
        else:
            data = response_body
    except json.JSONDecodeError:
        # If not JSON, cannot validate schema
        # For 5xx errors, non-JSON responses are invalid
        if status_code >= 500:
            return False, ["Response body is not valid JSON for 5xx error"]
        return True, []
    except:
        # Other parsing errors
        if status_code >= 500:
            return False, ["Cannot parse response body for 5xx error"]
        return True, []
    
    # Define schema expectations per status code
    # For 5xx errors, expect error and message fields
    if status_code >= 500:
        if not isinstance(data, dict):
            return False, ["Response body must be a JSON object for 5xx errors"]
        if "error" not in data:
            return False, ["Missing 'error' field in 5xx error response"]
        if "message" not in data:
            return False, ["Missing 'message' field in 5xx error response"]
        # Optionally validate types
        if not isinstance(data.get("error"), str):
            return False, ["Field 'error' must be a string"]
        if not isinstance(data.get("message"), str):
            return False, ["Field 'message' must be a string"]
        # Additional validation: error should be "Internal Server Error" for 500?
        # We'll be lenient, just ensure it's present.
    # For 4xx errors, similar structure but optional
    elif 400 <= status_code < 500:
        if isinstance(data, dict):
            if "error" in data and not isinstance(data["error"], str):
                return False, ["Field 'error' must be a string"]
            if "message" in data and not isinstance(data["message"], str):
                return False, ["Field 'message' must be a string"]
    # For 2xx success, no schema validation by default (could be added later)
    
    return True, []

app = Flask(__name__)
CORS(app)

generator = generate_testcases()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/generate', methods=['POST'])
def generate_test_cases():
    try:
        data = request.get_json()
        print(f"Received generation request data: {json.dumps(data, indent=2)}")
        test_cases = generator.generate_test_cases(data)
        return jsonify({
            'success': True,
            'test_cases': test_cases,
            'count': len(test_cases)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/test-cases', methods=['GET'])
def get_test_cases():
    try:
        test_cases = generator.get_test_cases()
        return jsonify({
            'success': True,
            'test_cases': test_cases,
            'count': len(test_cases)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'app': 'API Test Case Generator v3'
    })

def extract_response_code(expected_input):
    """
    Extract HTTP status codes from expected input.
    Handles both string format (Excel test cases) and list format (database test cases).
    
    Args:
        expected_input: Can be string like "201 Created" or list like ["201", "200"]
    
    Returns:
        List of status code strings
    """
    if not expected_input:
        return ["N/A"]
    
    # If it's already a list, return it directly (database test cases)
    if isinstance(expected_input, list):
        # Filter out any non-string elements and ensure they're valid status codes
        valid_codes = []
        for item in expected_input:
            if item is None:
                continue
            item_str = str(item).strip()
            # Check if it's a 3-digit HTTP status code
            if re.match(r'^[1-5]\d{2}$', item_str):
                valid_codes.append(item_str)
            elif item_str.upper() != "N/A":
                # Try to extract codes from the string
                matches = re.findall(r'\b([1-5]\d{2})\b', item_str)
                valid_codes.extend(matches)
        
        if valid_codes:
            return valid_codes
        else:
            return ["N/A"]
    
    # Handle string input (Excel test cases)
    expected_str = str(expected_input)
    
    # Look for all 3-digit numbers starting with 1-5 (standard HTTP status codes)
    matches = re.findall(r'\b([1-5]\d{2})\b', expected_str)
    if matches:
        return matches
    
    # Fallback to keywords if no 3-digit code is found
    expected_lower = expected_str.lower()
    if 'created' in expected_lower:
        return ["201"]
    if 'no content' in expected_lower:
        return ["204"]
    if 'success' in expected_lower or 'ok' in expected_lower:
        return ["200"]
    if 'bad request' in expected_lower or 'invalid' in expected_lower or 'missing' in expected_lower:
        return ["400"]
    if 'unauthorized' in expected_lower:
        return ["401"]
    if 'forbidden' in expected_lower:
        return ["403"]
    if 'not found' in expected_lower:
        return ["404"]
    if 'conflict' in expected_lower:
        return ["409"]
    if 'too many' in expected_lower or 'rate limit' in expected_lower:
        return ["429"]
    return ["N/A"]

def format_expected_for_display(expected):
    """Format expected status for display in logs."""
    if not expected:
        return "N/A"
    
    # If it's already a list (like ['201', '200']), format it nicely
    if isinstance(expected, list):
        if len(expected) == 1:
            return expected[0]
        else:
            return ", ".join(expected)
    
    # If it's a string, return as is
    return str(expected)

def get_test_case_source_info(test_case):
    """Get source information and additional details for a test case."""
    source = "excel"
    additional_info = []
    
    # Check for database-specific fields
    if test_case.get('expected_status') is not None:
        source = "database"
    
    if test_case.get('test_case_id'):
        additional_info.append(f"DB ID: {test_case['test_case_id']}")
    
    if test_case.get('test_case_number'):
        additional_info.append(f"Test #: {test_case['test_case_number']}")
    
    if test_case.get('metadata'):
        metadata = test_case['metadata']
        if isinstance(metadata, dict):
            if metadata.get('source'):
                source = metadata['source']
            if metadata.get('session_id'):
                additional_info.append(f"Session: {metadata['session_id']}")
    
    return source, additional_info

def format_input_body(input_data):
    if isinstance(input_data, dict):
        return json.dumps(input_data, indent=2)
    elif isinstance(input_data, list):
        return json.dumps(input_data, indent=2)
    else:
        return str(input_data)

@app.route('/api/export-excel', methods=['POST'])
def export_excel():
    try:
        data = request.get_json()
        print(f"[DEBUG] export-excel received data: {data}")
        test_cases = generator.generate_test_cases(data)
        print(f"[DEBUG] Generated {len(test_cases)} test cases")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "API Test Cases"

        header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        headers = ["ID", "HTTP Method", "Test Case Name", "Test Type", "Base Url", "Endpoint", "Request Body", "Expected Response Code", "Expected Status", "Status"]
        ws.append(headers)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = border

        http_method = data.get('method', 'GET')
        
        for tc in test_cases:
            request_body = format_input_body(tc.get("input", {}))
            response_codes = extract_response_code(tc.get("expected", ""))
            # Convert list to comma-separated string for Excel
            response_code_str = ", ".join(response_codes) if isinstance(response_codes, list) else str(response_codes)
            
            ws.append([
                tc.get("id"),
                http_method,
                tc.get("scenario"),
                tc.get("type"),
                tc.get("baseUrl", data.get("baseUrl", "")),
                data.get("endpoint", "/api/test"),
                request_body,
                response_code_str,
                tc.get("expected"),
                "" # Status
            ])

        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 20
        ws.column_dimensions['G'].width = 50
        ws.column_dimensions['H'].width = 16
        ws.column_dimensions['I'].width = 30
        ws.column_dimensions['J'].width = 10

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        endpoint = data.get('endpoint', '/api/test')
        endpoint_clean = endpoint.strip('/').replace('/', '_').replace(' ', '_').upper()
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H-%M-%S')
        filename = f"{http_method}_{endpoint_clean}_TestCases_{date_str}_{time_str}.xlsx"
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/save-to-database', methods=['POST'])
def save_to_database():
    """
    Save generated test cases to SQL Server database.
    Request body: same as /api/export-excel
    Response: { success: bool, session_id: str, message: str, saved_count: int }
    """
    try:
        data = request.get_json()
        print(f"[DEBUG] save-to-database received data: {data}")
        
        # Generate test cases
        test_cases = generator.generate_test_cases(data)
        print(f"[DEBUG] Generated {len(test_cases)} test cases for database save")
        
        if not test_cases:
            return jsonify({
                'success': False,
                'message': 'No test cases generated to save'
            }), 400
        
        # Prepare session data
        session_data = {
            'endpoint': data.get('endpoint', '/api/test'),
            'method': data.get('method', 'GET'),
            'base_url': data.get('baseUrl', data.get('base_url', '')),
            'session_name': data.get('session_name', f"Test Cases {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
            'created_by': 'system'
        }
        
        # Save to database
        db = get_database()
        success, message, session_id, saved_count = db.save_test_cases(session_data, test_cases)
        
        if success:
            return jsonify({
                'success': True,
                'session_id': session_id,
                'message': message,
                'saved_count': saved_count
            })
        else:
            return jsonify({
                'success': False,
                'message': message,
                'saved_count': saved_count
            }), 500
            
    except Exception as e:
        error_msg = f"Database save error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/database-sessions', methods=['GET'])
def get_database_sessions():
    """
    Retrieve saved test case sessions.
    Query params: limit, offset, endpoint, base_url, method (optional filters)
    Response: { sessions: [], total: int }
    """
    try:
        limit = request.args.get('limit', default=50, type=int)
        offset = request.args.get('offset', default=0, type=int)
        endpoint_filter = request.args.get('endpoint', default=None, type=str)
        base_url_filter = request.args.get('base_url', default=None, type=str)
        method_filter = request.args.get('method', default=None, type=str)
        
        db = get_database()
        sessions, total = db.get_sessions(
            limit=limit,
            offset=offset,
            endpoint_filter=endpoint_filter,
            base_url_filter=base_url_filter,
            method_filter=method_filter
        )
        
        return jsonify({
            'success': True,
            'sessions': sessions,
            'total': total,
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        error_msg = f"Failed to retrieve sessions: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/database-test-cases/<session_id>', methods=['GET'])
def get_session_test_cases(session_id):
    """
    Retrieve test cases for a specific session.
    Response: { session_info: {}, test_cases: [] }
    """
    try:
        db = get_database()
        session_info, test_cases = db.get_test_cases(session_id)
        
        if session_info is None:
            return jsonify({
                'success': False,
                'message': f"Session {session_id} not found"
            }), 404
        
        return jsonify({
            'success': True,
            'session_info': session_info,
            'test_cases': test_cases,
            'count': len(test_cases)
        })
        
    except Exception as e:
        error_msg = f"Failed to retrieve test cases: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/database-health', methods=['GET'])
def database_health():
    """
    Check database connection health.
    Response: { success: bool, message: str }
    """
    try:
        success, message = initialize_database()
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Database health check failed: {str(e)}"
        }), 500

@app.route('/api/download-excel', methods=['POST'])
def download_excel():
    try:
        data = request.get_json()
        test_cases = data.get('test_cases', [])
        endpoint = data.get('endpoint', '/api/test')
        method = data.get('method', 'GET')
        
        if not test_cases:
            return jsonify({
                'success': False,
                'error': 'No test cases provided'
            }), 400

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "API Test Cases"

        header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        headers = ["ID", "HTTP Method", "Test Case Name", "Test Type", "Endpoint", "Request Body", "Expected Response Code", "Expected Status", "Status"]
        ws.append(headers)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = border

        for tc in test_cases:
            request_body = format_input_body(tc.get("input", {}))
            response_codes = extract_response_code(tc.get("expected", ""))
            # Convert list to comma-separated string for Excel
            response_code_str = ", ".join(response_codes) if isinstance(response_codes, list) else str(response_codes)
            
            ws.append([
                tc.get("id"),
                method,
                tc.get("scenario"),
                tc.get("type"),
                tc.get("baseUrl", ""),
                endpoint,
                request_body,
                response_code_str,
                tc.get("expected"),
                "" # Empty Status column
            ])

        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 20
        ws.column_dimensions['G'].width = 50
        ws.column_dimensions['H'].width = 16
        ws.column_dimensions['I'].width = 30
        ws.column_dimensions['J'].width = 10

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        endpoint_clean = endpoint.strip('/').replace('/', '_').replace(' ', '_').upper()
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H-%M-%S')
        filename = f"{method}_{endpoint_clean}_TestCases_{date_str}_{time_str}.xlsx"
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/export-results', methods=['POST'])
def export_results():
    try:
        data = request.get_json()
        results = data.get('results', [])
        test_cases = data.get('test_cases', [])
        endpoint = data.get('endpoint', '/api/test')
        method = data.get('method', 'GET')
        
        if not results:
            return jsonify({
                'success': False,
                'error': 'No results provided'
            }), 400

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "API Test Results"

        header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        headers = ["ID", "HTTP Method", "Test Case Name", "Test Type", "Base Url", "Endpoint", "Request Body", "Expected Status", "Actual Status", "Result", "Response Body", "Details"]
        ws.append(headers)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = border

        # Create a map for quick lookup of test cases by ID
        tc_map = {tc.get('id'): tc for tc in test_cases}

        for res in results:
            tc_id = res.get('testCaseId')
            tc = tc_map.get(tc_id, {})
            
            request_body = format_input_body(tc.get("input", {}))
            status = res.get('status', 'fail').upper()
            
            row_data = [
                tc_id,
                method,
                tc.get("scenario", "N/A"),
                tc.get("type", "N/A"),
                tc.get("baseUrl", ""),
                endpoint,
                request_body,
                tc.get("expected", "N/A"),
                res.get('statusCode', 'N/A'),
                status,
                res.get('responseBody', ''),
                res.get('details', '')
            ]
            ws.append(row_data)
            
            # Color coding the result cell
            last_row = ws.max_row
            result_cell = ws.cell(row=last_row, column=10)
            if status == 'PASS':
                result_cell.fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
                result_cell.font = Font(color="065F46", bold=True)
            else:
                result_cell.fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
                result_cell.font = Font(color="991B1B", bold=True)

        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # Set column widths
        ws.column_dimensions['A'].width = 15
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 20
        ws.column_dimensions['G'].width = 40
        ws.column_dimensions['H'].width = 25
        ws.column_dimensions['I'].width = 15
        ws.column_dimensions['J'].width = 12
        ws.column_dimensions['K'].width = 40
        ws.column_dimensions['L'].width = 50

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        endpoint_clean = endpoint.strip('/').replace('/', '_').replace(' ', '_').upper()
        now = datetime.now()
        filename = f"RESULTS_{method}_{endpoint_clean}_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"[ERROR] export-excel failed: {str(e)}")
        print(f"[ERROR] Traceback:\n{error_details}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/upload-excel', methods=['POST'])
def upload_excel():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'}), 400
        
        if file and file.filename.endswith(('.xlsx', '.xls')):
            wb = openpyxl.load_workbook(file)
            ws = wb.active
            
            test_cases = []
            headers = [cell.value for cell in ws[1]]
            
            # Find column indices
            col_map = {
                'id': -1, 'method': -1, 'scenario': -1, 'type': -1, 
                'endpoint': -1, 'input': -1, 'expected': -1, 'baseUrl': -1
            }
            
            for i, header in enumerate(headers):
                if not header: continue
                h = header.lower()
                if 'id' in h: col_map['id'] = i
                elif 'method' in h: col_map['method'] = i
                elif 'name' in h or 'scenario' in h: col_map['scenario'] = i
                elif 'type' in h: col_map['type'] = i
                elif 'base' in h and 'url' in h: col_map['baseUrl'] = i
                elif 'endpoint' in h: col_map['endpoint'] = i
                elif 'body' in h or 'input' in h: col_map['input'] = i
                elif 'expected status' in h or 'expected response' in h or 'expected' in h: 
                    if col_map['expected'] == -1 or 'status' in h:
                        col_map['expected'] = i

            for row in ws.iter_rows(min_row=2, values_only=True):
                tc = {}
                if col_map['id'] != -1: tc['id'] = str(row[col_map['id']]) if row[col_map['id']] else f"TC_{len(test_cases)+1}"
                else: tc['id'] = f"TC_{len(test_cases)+1}"
                
                tc['method'] = str(row[col_map['method']]) if col_map['method'] != -1 and row[col_map['method']] else "GET"
                tc['scenario'] = str(row[col_map['scenario']]) if col_map['scenario'] != -1 and row[col_map['scenario']] else "Test Case"
                tc['type'] = str(row[col_map['type']]) if col_map['type'] != -1 and row[col_map['type']] else "Positive"
                tc['endpoint'] = str(row[col_map['endpoint']]) if col_map['endpoint'] != -1 and row[col_map['endpoint']] else "/"
                tc['baseUrl'] = str(row[col_map['baseUrl']]) if col_map['baseUrl'] != -1 and row[col_map['baseUrl']] else ""
                
                input_val = row[col_map['input']] if col_map['input'] != -1 else "{}"
                try:
                    if isinstance(input_val, str):
                        tc['input'] = json.loads(input_val)
                    else:
                        tc['input'] = input_val if input_val else {}
                except:
                    tc['input'] = input_val if input_val else {}
                    
                tc['expected'] = str(row[col_map['expected']]) if col_map['expected'] != -1 and row[col_map['expected']] else "200 OK"
                
                test_cases.append(tc)

            return jsonify({
                'success': True,
                'test_cases': test_cases,
                'count': len(test_cases)
            })
        
        return jsonify({'success': False, 'error': 'Invalid file format'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/execute-tests', methods=['POST'])
def execute_tests():
    try:
        data = request.get_json()
        print (f"Received test execution request: {json.dumps(data, indent=2)}")
        endpoint = data.get('endpoint', '').strip()
        method = data.get('method', 'GET').upper()
        test_cases = data.get('testCases', [])
        environment = data.get('environment', 'mock')
        base_url = data.get('baseUrl') or data.get('base_url') or 'mock'

        if not endpoint:
            return jsonify({
                'success': False,
                'error': 'Endpoint is required'
            }), 400

        if not test_cases:
            return jsonify({
                'success': False,
                'error': 'No test cases provided'
            }), 400

        results = []
        original_payload = data.get('originalPayload')
        
        # Parse original_payload if it's a string
        if isinstance(original_payload, str) and original_payload.strip():
            try:
                original_payload = json.loads(original_payload)
            except:
                pass # Keep as string if not valid JSON

        field_configs = data.get('fieldConfigs', {})
        for test_case in test_cases:
            result = execute_single_test(endpoint, method, test_case, environment, base_url, original_payload, field_configs)
            results.append(result)

        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

def generate_mock_response(test_case, method, original_payload=None, field_configs=None):
    expected = test_case.get('expected', 'Success response')
    
    # For database test cases, check for expected_status field
    if expected == 'N/A' or not expected:
        expected = test_case.get('expected_status', 'N/A')
    
    test_type = test_case.get('type', 'Positive')
    scenario = test_case.get('scenario', '')
    payload = test_case.get('input', {})
    
    # Extract expected status code if available
    expected_codes = extract_response_code(expected)
    validation_errors = []
    
    # Priority validation against explicit user configurations
    if field_configs:
        source = 'query' if method == 'GET' else 'body'
        is_valid, errors = validate_against_configs(payload, field_configs, source=source)
        if not is_valid:
            validation_errors = errors

    # Fallback validation against original payload types
    if not validation_errors and test_type == 'Positive' and original_payload:
        source = 'query' if method == 'GET' else 'body'
        if source == 'query':
            # For query params, parse them first for type validation
            parsed_payload = parse_query_params(payload)
            is_valid, errors = validate_input_types(parsed_payload, original_payload)
        else:
            is_valid, errors = validate_input_types(payload, original_payload)
            
        if not is_valid:
            validation_errors = errors

    if validation_errors:
        error_msg = "\n".join([f"• {err}" for err in validation_errors])
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Bad Request", "message": "Please correct the following validation errors and try again.", "details": validation_errors}),
            'expected': expected,
            'validation_failed': True,
            'validation_error': f"❌ Invalid data type\n\nPlease correct the following validation errors and try again.\n\n{error_msg}"
        }

    # Handle expected codes - take the first one if available and not "N/A"
    if expected_codes and "N/A" not in expected_codes:
        try:
            # Take the first expected code for mock response
            first_code = expected_codes[0]
            status_code = int(first_code)
            
            # Select appropriate mock body based on status code
            if 200 <= status_code < 300:
                if status_code == 204:
                    body = ""
                elif method in ['POST', 'PUT', 'PATCH']:
                    if original_payload and isinstance(original_payload, (dict, list)):
                        # If we have an original payload, return it as the mock response for realism
                        body = json.dumps(original_payload)
                    else:
                        body = json.dumps({"message": "Resource processed successfully", "id": "mock_001", "status": "success"})
                else:
                    # For GET/others, return realistic data if available
                    if original_payload and isinstance(original_payload, (dict, list)):
                        # For GET/others, if original was a list, return list. If original was object, return as list of one for typical GET list APIs
                        if isinstance(original_payload, list):
                            body = json.dumps(original_payload)
                        else:
                            body = json.dumps([original_payload])
                    else:
                        body = json.dumps({"status": "success", "data": []})
            elif status_code == 401:
                body = json.dumps({"error": "Unauthorized", "message": "Missing or invalid authentication token"})
            elif status_code == 403:
                body = json.dumps({"error": "Forbidden", "message": "You do not have permission to access this resource"})
            elif status_code == 404:
                body = json.dumps({"error": "Not Found", "message": "The requested resource was not found"})
            elif status_code == 409:
                body = json.dumps({"error": "Conflict", "message": "Resource already exists or state conflict"})
            elif status_code == 415:
                body = json.dumps({"error": "Unsupported Media Type", "message": "Content-Type header is missing or invalid"})
            elif status_code == 429:
                body = json.dumps({"error": "Too Many Requests", "message": "Rate limit exceeded"})
            elif 400 <= status_code < 500:
                body = json.dumps({"error": "Bad Request", "message": expected})
            elif status_code >= 500:
                body = json.dumps({"error": "Internal Server Error", "message": "An unexpected error occurred on the server"})
            else:
                body = json.dumps({"status": "mock_response", "code": status_code})
                
            return {
                'statusCode': status_code,
                'body': body,
                'expected': expected
            }
        except:
            pass

    # Fallback to legacy logic based on test type if extraction fails
    if test_type in ['Positive', 'Integration', 'Performance']:
        if method == 'POST':
            body = json.dumps(original_payload) if original_payload and isinstance(original_payload, (dict, list)) else json.dumps({"message": "Resource created successfully", "id": "mock_001"})
            return {'statusCode': 201, 'body': body, 'expected': expected}
        elif method == 'DELETE':
            return {'statusCode': 204, 'body': '', 'expected': expected}
        else:
            if original_payload and isinstance(original_payload, (dict, list)):
                body = json.dumps(original_payload) if isinstance(original_payload, list) else json.dumps([original_payload])
            else:
                body = json.dumps({"status": "success", "data": []})
            return {'statusCode': 200, 'body': body, 'expected': expected}
    
    elif test_type in ['Negative', 'Validation', 'Security', 'Header', 'Auth', 'RateLimit']:
        status_code = 400
        error_msg = "Bad Request"
        
        if test_type == 'Auth' or 'Authorization' in scenario or 'token' in scenario.lower():
            status_code = 401
            error_msg = "Unauthorized"
        elif 'Forbidden' in scenario or 'Role' in scenario or 'Permission' in scenario:
            status_code = 403
            error_msg = "Forbidden"
        elif 'Not Found' in scenario or 'non-existing' in scenario:
            status_code = 404
            error_msg = "Not Found"
        elif 'Rate' in scenario or 'Limit' in scenario:
            status_code = 429
            error_msg = "Too Many Requests"
        elif 'Content-Type' in scenario or 'Header' in test_type:
            status_code = 415
            error_msg = "Unsupported Media Type"
            
        return {
            'statusCode': status_code, 
            'body': json.dumps({"error": error_msg, "message": scenario}), 
            'expected': expected
        }
        
    return {
        'statusCode': 200, 
        'body': json.dumps({"status": "mock_response", "scenario": scenario}), 
        'expected': expected
    }

def execute_single_test(endpoint, method, test_case, environment='mock', base_url='mock', original_payload=None, field_configs=None):
    test_id = test_case.get('id', 'Unknown')
    expected = test_case.get('expected', 'N/A')
    
    # For database test cases, check for expected_status field
    if expected == 'N/A' or not expected:
        expected = test_case.get('expected_status', 'N/A')
    
    # Get test case source information early (for both success and error returns)
    source, additional_info = get_test_case_source_info(test_case)
    
    # Prioritize the passed base_url if it's a real URL provided in the execution request
    # This allows users to change environment/URL in the UI and run existing tests against it
    if not base_url or base_url == 'mock':
        base_url = test_case.get('baseUrl', base_url)
    
    # Use method and endpoint from test case if available (important for Excel uploads and database test cases)
    method = test_case.get('method', method).upper()
    endpoint = test_case.get('endpoint', endpoint)
    
    # If payload (input) is a path parameter (starts with /), it should override the endpoint
    # For query parameters (starts with ?), it should be appended to the endpoint
    current_endpoint = endpoint
    payload = test_case.get('input', {})
    
    if isinstance(payload, str) and payload.startswith('/'):
        current_endpoint = payload
    
    if environment == 'mock' or base_url == 'mock':
        return execute_mock_test(test_id, method, test_case, expected, original_payload, field_configs, base_url, current_endpoint)
    
    try:
        url = build_url(current_endpoint, base_url)
        headers = {'Content-Type': 'application/json'}
        
        # Validation against field configurations
        if field_configs:
            source = 'query' if method == 'GET' else 'body'
            is_valid, errors = validate_against_configs(payload, field_configs, source=source)
            if not is_valid:
                error_summary = "\n".join([f"• {err}" for err in errors])
                full_msg = f"❌ Invalid data type\n\nPlease correct the following validation errors and try again.\n\n{error_summary}"
                # For Positive cases, any validation error should fail the test
                expected_codes = extract_response_code(expected)
                status = 'fail' if test_case.get('type') == 'Positive' else ('pass' if '400' in expected_codes else 'fail')
                return {
                    'testCaseId': test_id,
                    'status': status,
                    'statusCode': 400,
                    'responseBody': json.dumps({"error": "Validation Error", "message": "Validation failed", "details": errors}),
                    'details': f"❌ Validation Error\n\n{full_msg}\n\nExpected: {expected}"
                }

        # Pre-validation of data types for Positive cases based on original payload
        if test_case.get('type') == 'Positive' and original_payload:
            source = 'query' if method == 'GET' else 'body'
            if source == 'query':
                parsed_payload = parse_query_params(payload)
                is_valid, errors = validate_input_types(parsed_payload, original_payload)
            else:
                is_valid, errors = validate_input_types(payload, original_payload)
                
            if not is_valid:
                error_summary = "\n".join([f"• {err}" for err in errors])
                full_msg = f"❌ Invalid data type\n\nPlease correct the following validation errors and try again.\n\n{error_summary}"
                return {
                    'testCaseId': test_id,
                    'status': 'fail',
                    'statusCode': 400,
                    'responseBody': json.dumps({"error": "Data Type Error", "message": "Type mismatch", "details": errors}),
                    'details': f"❌ Data Type Error\n\n{full_msg}\n\nExpected: {expected}"
                }

        try:
            if isinstance(payload, dict):
                payload_json = json.dumps(payload)
            elif isinstance(payload, list):
                payload_json = json.dumps(payload)
            elif payload is None:
                payload_json = None
            else:
                payload_json = str(payload)
        except:
            payload_json = str(payload)

        timeout = 10

        if method == 'GET':
            # If payload starts with / or ?, it's already handled in url or will be in params
            if isinstance(payload, str):
                if payload.startswith('/'):
                    # It was already merged into url via build_url(current_endpoint, ...)
                    response = requests.get(url, headers=headers, timeout=timeout)
                else:
                    params = parse_query_params(payload)
                    response = requests.get(url, params=params, headers=headers, timeout=timeout)
            else:
                response = requests.get(url, params=payload, headers=headers, timeout=timeout)
        elif method == 'POST':
            response = requests.post(url, data=payload_json, headers=headers, timeout=timeout)
        elif method == 'PUT':
            response = requests.put(url, data=payload_json, headers=headers, timeout=timeout)
        elif method == 'PATCH':
            response = requests.patch(url, data=payload_json, headers=headers, timeout=timeout)
        elif method == 'DELETE':
             # For DELETE, if payload is a path (starts with /), it's already in url
            if isinstance(payload, str) and payload.startswith('/'):
                response = requests.delete(url, headers=headers, timeout=timeout)
            else:
                response = requests.delete(url, data=payload_json, headers=headers, timeout=timeout)
        else:
            response = requests.request(method, url, data=payload_json, headers=headers, timeout=timeout)

        expected_codes = extract_response_code(expected)
        actual_code = str(response.status_code)
        
        if "N/A" in expected_codes:
            status = 'pass'
        elif actual_code in expected_codes:
            status = 'pass'
        else:
            status = 'fail'
        response_text = response.text[:1000] if response.text else '(No response body)'

        # Schema validation for 5xx errors
        schema_valid = True
        schema_errors = []
        if response.status_code >= 500:
            schema_valid, schema_errors = validate_response_schema(response.text, response.status_code)
            if not schema_valid:
                status = 'fail'  # Override status to fail if schema validation fails

        # Execution log printing
        print(f"\n--- Test Case Execution: {test_id} ---")
        print(f"Source: {source}")
        if additional_info:
            for info in additional_info:
                print(f"  {info}")
        print(f"Request URL: {response.url}")
        print(f"HTTP Method: {method}")
        print(f"Expected Status: {format_expected_for_display(expected)}")
        print(f"Actual Status: {response.status_code}")
        print(f"Response Body: {response.text}")
        print("-" * 40)

        # Build details with source information
        details_parts = [f"Request URL: {response.url}"]
        if additional_info:
            details_parts.append(f"Source: {source} ({', '.join(additional_info)})")
        else:
            details_parts.append(f"Source: {source}")
        details_parts.append(f"Expected: {format_expected_for_display(expected)}")
        details_parts.append(f"Actual: HTTP {response.status_code}")
        
        # Add schema validation results if validation failed
        if not schema_valid and schema_errors:
            details_parts.append(f"\nSchema Validation Failed:")
            for err in schema_errors:
                details_parts.append(f"  • {err}")
        
        details_parts.append(f"\nResponse:\n{response_text}")
        
        return {
            'testCaseId': test_id,
            'status': status,
            'statusCode': response.status_code,
            'responseBody': response.text if response.text else '',
            'details': "\n".join(details_parts),
            'source': source,
            'additionalInfo': additional_info
        }
    except requests.exceptions.Timeout:
        # Build details with source information for timeout
        details_parts = [f"❌ Connection Error: Request timeout after 10 seconds\n\nThe API endpoint took too long to respond. Check if the server is running and accessible."]
        if additional_info:
            details_parts.append(f"Source: {source} ({', '.join(additional_info)})")
        else:
            details_parts.append(f"Source: {source}")
        
        return {
            'testCaseId': test_id,
            'status': 'fail',
            'statusCode': 0,
            'details': "\n".join(details_parts),
            'source': source,
            'additionalInfo': additional_info
        }
    except requests.exceptions.ConnectionError as e:
        error_msg = str(e).lower()
        if 'getaddrinfo failed' in error_msg or 'name resolution' in error_msg:
            friendly_msg = f"❌ DNS Resolution Failed\n\nCannot resolve hostname. Verify:\n• Endpoint URL is correct\n• Network connection is active\n• DNS settings are configured properly"
        elif 'connection refused' in error_msg:
            friendly_msg = f"❌ Connection Refused\n\nThe server is not accepting connections. Verify:\n• Server is running on the specified port\n• Firewall rules allow the connection\n• Correct URL and port are configured"
        else:
            friendly_msg = f"❌ Connection Failed\n\n{str(e)[:200]}"
        
        # Build details with source information
        details_parts = [friendly_msg]
        if additional_info:
            details_parts.append(f"Source: {source} ({', '.join(additional_info)})")
        else:
            details_parts.append(f"Source: {source}")
        
        return {
            'testCaseId': test_id,
            'status': 'fail',
            'statusCode': 0,
            'details': "\n".join(details_parts),
            'source': source,
            'additionalInfo': additional_info
        }
    except Exception as e:
        # Build details with source information
        details_parts = [f"❌ Unexpected Error\n\n{str(e)[:300]}"]
        if additional_info:
            details_parts.append(f"Source: {source} ({', '.join(additional_info)})")
        else:
            details_parts.append(f"Source: {source}")
        
        return {
            'testCaseId': test_id,
            'status': 'fail',
            'statusCode': 0,
            'details': "\n".join(details_parts),
            'source': source,
            'additionalInfo': additional_info
        }

def execute_mock_test(test_id, method, test_case, expected, original_payload=None, field_configs=None, base_url='mock', current_endpoint=None):
    if current_endpoint is None:
        current_endpoint = test_case.get('endpoint', '')
        
    mock_response = generate_mock_response(test_case, method, original_payload, field_configs)
    status_code = mock_response['statusCode']
    expected_codes = extract_response_code(expected)
    actual_code = str(status_code)
    test_type = test_case.get('type', 'Positive')
    
    # If validation failed, it's only a pass if it's a Negative test that expected a 400
    if mock_response.get('validation_failed'):
        if test_type == 'Positive':
            status = 'fail'
        else:
            status = 'pass' if '400' in expected_codes else 'fail'
    else:
        if "N/A" in expected_codes:
            status = 'pass'
        elif actual_code in expected_codes:
            status = 'pass'
        else:
            status = 'fail'
    
    # Execution log printing (Mock Mode)
    payload = test_case.get('input', {})
    
    if base_url and base_url != 'mock':
        url = build_url(current_endpoint, base_url)
        # Use requests logic to build the exact URL if it's a GET request
        if method == 'GET' and isinstance(payload, str) and not payload.startswith('/'):
            params = parse_query_params(payload)
            # If the endpoint itself had query params, they'll be in 'url'
            # requests.Request will merge them with 'params'
            req = requests.Request('GET', url, params=params)
            prepared = req.prepare()
            mock_url = prepared.url
        else:
            mock_url = url
    else:
        # Fallback for mock environment without base_url
        if method == 'GET' and isinstance(payload, str) and payload.startswith('?'):
             mock_url = f"MOCK://{method}{current_endpoint}{payload}"
        else:
             mock_url = f"MOCK://{method}{current_endpoint}"

    # Get test case source information
    source, additional_info = get_test_case_source_info(test_case)
    
    print(f"\n--- [MOCK] Test Case Execution: {test_id} ---")
    print(f"Source: {source}")
    if additional_info:
        for info in additional_info:
            print(f"  {info}")
    print(f"Request URL: {mock_url}")
    print(f"HTTP Method: {method}")
    print(f"Expected Status: {format_expected_for_display(expected)}")
    print(f"Actual Status: {status_code}")
    print(f"Response Body: {mock_response['body']}")
    print("-" * 40)

    # Build details with source information
    details_parts = ["[MOCK MODE]"]
    if mock_response.get('validation_failed'):
        details_parts.append(mock_response['validation_error'])
    
    details_parts.append(f"Request URL: {mock_url}")
    
    if additional_info:
        details_parts.append(f"Source: {source} ({', '.join(additional_info)})")
    else:
        details_parts.append(f"Source: {source}")
    
    details_parts.append(f"Expected: {format_expected_for_display(expected)}")
    details_parts.append(f"Actual: HTTP {status_code}")
    details_parts.append(f"\nResponse:\n{mock_response['body']}")
    
    return {
        'testCaseId': test_id,
        'status': status,
        'statusCode': status_code,
        'responseBody': mock_response['body'],
        'details': "\n".join(details_parts),
        'source': source,
        'additionalInfo': additional_info
    }

def build_url(endpoint, base_url):
    if not endpoint:
        endpoint = ""
    if not base_url:
        base_url = ""
        
    if endpoint.startswith('http'):
        return endpoint
        
    if base_url.startswith('http'):
        # Ensure base_url ends with slash if endpoint doesn't start with one,
        # but only if endpoint isn't just a query string
        base = base_url.rstrip('/')
        if endpoint.startswith('?'):
            return base + endpoint
        return base + '/' + endpoint.lstrip('/')
        
    return f'http://localhost:5000/{endpoint.lstrip("/")}'

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
