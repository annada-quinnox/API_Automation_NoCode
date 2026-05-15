"""
Database module for API Test Command Center.
Handles SQL Server database operations for saving and retrieving test cases.
"""

import pyodbc
import json
import uuid
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple


class TestCaseDatabase:
    """Database operations for test case storage."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize database connection.
        
        Args:
            config: Database configuration dictionary with keys:
                   - server: SQL Server name (e.g., 'LPT2149-B1')
                   - database: Database name (e.g., 'API_Test_Cases')
                   - username: Username (e.g., 'testUser1')
                   - password: Password (e.g., 'TestUser@1')
                   - driver: ODBC driver (default: '{ODBC Driver 17 for SQL Server}')
        """
        if config is None:
            config = self._get_default_config()
        
        self.config = config
        self.connection_string = self._build_connection_string(config)
        
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default database configuration."""
        return {
            'server': 'LPT2149-B1',
            'database': 'TestCasesDB',
            'driver': '{ODBC Driver 17 for SQL Server}',
            'use_windows_auth': True  # Use Windows Authentication
        }
    
    def _build_connection_string(self, config: Dict[str, Any]) -> str:
        """Build ODBC connection string from configuration."""
        driver = config.get('driver', '{ODBC Driver 17 for SQL Server}')
        server = config['server']
        database = config['database']
        
        # Build base connection string
        conn_str = f"DRIVER={driver};SERVER={server};DATABASE={database};"
        
        # Add authentication method
        if config.get('use_windows_auth', True):
            # Windows Authentication (Trusted Connection)
            conn_str += "Trusted_Connection=yes;"
        else:
            # SQL Server Authentication
            username = config.get('username', '')
            password = config.get('password', '')
            if username and password:
                conn_str += f"UID={username};PWD={password};"
            else:
                # Fall back to Windows Auth if no credentials provided
                conn_str += "Trusted_Connection=yes;"
        
        # Add additional options for better compatibility
        conn_str += "TrustServerCertificate=yes;"
        
        return conn_str
    
    def _generate_table_name(self, base_url: str, endpoint: str, method: str) -> str:
        """
        Generate a table name from base URL, endpoint, and HTTP method.
        
        Args:
            base_url: Base URL (e.g., 'https://petstore.swagger.io/v2')
            endpoint: API endpoint (e.g., '/pet/')
            method: HTTP method (e.g., 'POST')
            
        Returns:
            Valid SQL Server table name
        """
        # Normalize base_url: remove protocol, replace special chars
        if base_url:
            # Remove http:// or https://
            if base_url.startswith('http://'):
                base_url = base_url[7:]
            elif base_url.startswith('https://'):
                base_url = base_url[8:]
            
            # Replace dots, slashes, and other special chars with underscores
            base_url_clean = ''.join(c if c.isalnum() else '_' for c in base_url)
            # Remove consecutive underscores
            while '__' in base_url_clean:
                base_url_clean = base_url_clean.replace('__', '_')
            # Remove leading/trailing underscores
            base_url_clean = base_url_clean.strip('_')
        else:
            base_url_clean = 'default'
        
        # Normalize endpoint: remove leading slash, replace special chars
        if endpoint:
            endpoint_clean = endpoint.lstrip('/')
            endpoint_clean = ''.join(c if c.isalnum() else '_' for c in endpoint_clean)
            while '__' in endpoint_clean:
                endpoint_clean = endpoint_clean.replace('__', '_')
            endpoint_clean = endpoint_clean.strip('_')
        else:
            endpoint_clean = 'root'
        
        # Method is already clean (GET, POST, PUT, DELETE, PATCH)
        method_clean = method.upper()
        
        # Combine and ensure table name is valid (max 128 chars in SQL Server)
        table_name = f"test_cases_{base_url_clean}_{endpoint_clean}_{method_clean}"
        
        # Truncate if too long
        if len(table_name) > 128:
            # Keep first 100 chars and add hash of full name
            import hashlib
            hash_part = hashlib.md5(table_name.encode()).hexdigest()[:8]
            table_name = table_name[:100] + '_' + hash_part
        
        return table_name
    
    def _ensure_table_exists(self, table_name: str, cursor) -> bool:
        """
        Ensure a test cases table exists. If table already exists,
        delete it and recreate it with the new test cases.
        
        Args:
            table_name: Name of the table to check/create
            cursor: Database cursor
            
        Returns:
            True if table exists or was created successfully
        """
        try:
            # Check if table exists
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = '{table_name}'
            """)
            
            table_exists = cursor.fetchone()[0] > 0
            
            if table_exists:
                # Table exists, delete it and related session records
                print(f"Table '{table_name}' already exists. Deleting and recreating...")
                
                # First drop the table (removes foreign key constraint)
                cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
                print(f"Dropped existing table '{table_name}'")
                
                # Now delete any session records that reference this table
                cursor.execute("""
                    DELETE FROM test_case_sessions
                    WHERE table_name = ?
                """, table_name)
                print(f"Deleted session records referencing table '{table_name}'")
            
            # Create the table (whether it existed or not)
            print(f"Creating table '{table_name}'...")
            cursor.execute(f"""
                CREATE TABLE [{table_name}] (
                    test_case_id NVARCHAR(50) PRIMARY KEY,
                    session_id NVARCHAR(50),
                    test_case_number INT NOT NULL,
                    test_type NVARCHAR(50) NOT NULL,
                    scenario NVARCHAR(MAX) NOT NULL,
                    input_body NVARCHAR(MAX),
                    expected_response NVARCHAR(MAX),
                    expected_status_codes NVARCHAR(100),
                    base_url NVARCHAR(1000),
                    endpoint NVARCHAR(1000),
                    http_method NVARCHAR(10),
                    metadata NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (session_id) REFERENCES test_case_sessions(session_id)
                )
            """)
            
            # Create index on session_id
            cursor.execute(f"""
                CREATE INDEX idx_{table_name}_session_id
                ON [{table_name}](session_id)
            """)
            
            print(f"Table '{table_name}' created successfully")
            
            return True
            
        except Exception as e:
            print(f"Error ensuring table '{table_name}' exists: {e}")
            return False
    
    def _extract_response_code(self, expected_str: str) -> str:
        """
        Extract HTTP status codes from expected response string.
        This matches the logic used in app.py's extract_response_code function.
        
        Args:
            expected_str: The expected response string
            
        Returns:
            Comma-separated string of status codes (e.g., "200,201") or "N/A"
        """
        if not expected_str:
            return "N/A"
        
        # Look for all 3-digit numbers starting with 1-5 (standard HTTP status codes)
        matches = re.findall(r'\b([1-5]\d{2})\b', str(expected_str))
        if matches:
            return ",".join(matches)
        
        # Fallback to keywords if no 3-digit code is found
        expected_lower = str(expected_str).lower()
        if 'created' in expected_lower:
            return "201"
        if 'no content' in expected_lower:
            return "204"
        if 'success' in expected_lower or 'ok' in expected_lower:
            return "200"
        if 'bad request' in expected_lower or 'invalid' in expected_lower or 'missing' in expected_lower:
            return "400"
        if 'unauthorized' in expected_lower:
            return "401"
        if 'forbidden' in expected_lower:
            return "403"
        if 'not found' in expected_lower:
            return "404"
        if 'conflict' in expected_lower:
            return "409"
        if 'too many' in expected_lower or 'rate limit' in expected_lower:
            return "429"
        return "N/A"
    
    def get_connection(self):
        """Get a new database connection."""
        try:
            return pyodbc.connect(self.connection_string)
        except pyodbc.Error as e:
            raise ConnectionError(f"Failed to connect to database: {str(e)}")
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test database connection and ensure tables exist.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # First try to connect to the target database
            try:
                conn = self.get_connection()
                cursor = conn.cursor()

                def fetch_scalar() -> int:
                    row = cursor.fetchone()
                    return int(row[0]) if row and row[0] is not None else 0
                
                # Check if test_case_sessions table exists
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_NAME = 'test_case_sessions'
                """)
                table_count = fetch_scalar()
                
                if table_count == 1:
                    # Check if table_name column exists
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'test_case_sessions' AND COLUMN_NAME = 'table_name'
                    """)
                    column_count = fetch_scalar()
                    
                    if column_count == 1:
                        conn.close()
                        return True, "Database connection successful, sessions table exists with table_name column"
                    else:
                        # Column is missing, need to upgrade schema
                        print("Table exists but missing table_name column, upgrading schema...")
                        # Add the column
                        cursor.execute("""
                            ALTER TABLE test_case_sessions ADD table_name NVARCHAR(255) NULL
                        """)
                        cursor.execute("""
                            UPDATE test_case_sessions SET table_name = 'test_cases' WHERE table_name IS NULL
                        """)
                        cursor.execute("""
                            ALTER TABLE test_case_sessions ALTER COLUMN table_name NVARCHAR(255) NOT NULL
                        """)
                        conn.commit()
                        conn.close()
                        return True, "Database schema upgraded successfully, added table_name column"
                else:
                    # Tables don't exist, create them
                    conn.close()
                    return self._create_database_and_tables()
                    
            except pyodbc.Error as e:
                # If connection fails, check if database doesn't exist
                error_msg = str(e)
                if "Cannot open database" in error_msg or "database .* requested by the login" in error_msg:
                    # Database doesn't exist, try to create it
                    return self._create_database_and_tables()
                else:
                    # Other connection error
                    return False, f"Database connection failed: {error_msg}"
                
        except Exception as e:
            return False, f"Database connection failed: {str(e)}"
    
    def _create_database_and_tables(self) -> Tuple[bool, str]:
        """
        Create database and tables if they don't exist.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Connect to master database
            master_config = self.config.copy()
            master_config['database'] = 'master'
            master_conn_str = self._build_connection_string(master_config)
            
            conn = pyodbc.connect(master_conn_str)
            cursor = conn.cursor()
            conn.autocommit = True
            
            db_name = self.config['database']
            
            # Check if database exists
            cursor.execute(f"SELECT name FROM sys.databases WHERE name = '{db_name}'")
            if cursor.fetchone():
                print(f"Database '{db_name}' already exists")
            else:
                # Create database
                print(f"Creating database '{db_name}'...")
                cursor.execute(f"CREATE DATABASE [{db_name}]")
                print(f"Database '{db_name}' created successfully")
            
            conn.close()
            
            # Now connect to the new database and create tables
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create test_case_sessions table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='test_case_sessions' AND xtype='U')
                CREATE TABLE test_case_sessions (
                    session_id NVARCHAR(50) PRIMARY KEY,
                    session_name NVARCHAR(255) NOT NULL,
                    endpoint NVARCHAR(1000) NOT NULL,
                    http_method NVARCHAR(10) NOT NULL,
                    base_url NVARCHAR(1000),
                    created_by NVARCHAR(100),
                    created_at DATETIME DEFAULT GETDATE(),
                    total_test_cases INT DEFAULT 0,
                    table_name NVARCHAR(255) NOT NULL
                )
            """)
            
            # Check if table_name column exists, add it if missing
            cursor.execute("""
                IF NOT EXISTS (
                    SELECT * FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'test_case_sessions' AND COLUMN_NAME = 'table_name'
                )
                BEGIN
                    -- First add as nullable
                    ALTER TABLE test_case_sessions ADD table_name NVARCHAR(255) NULL
                    -- Set default value for existing rows
                    UPDATE test_case_sessions SET table_name = 'test_cases' WHERE table_name IS NULL
                    -- Now alter to NOT NULL
                    ALTER TABLE test_case_sessions ALTER COLUMN table_name NVARCHAR(255) NOT NULL
                END
            """)
            
            # Note: We no longer create a generic test_cases table here
            # Dynamic tables will be created by _ensure_table_exists when needed
            
            # Create indexes
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_test_case_sessions_created_at')
                CREATE INDEX idx_test_case_sessions_created_at ON test_case_sessions(created_at DESC)
            """)
            
            conn.commit()
            conn.close()
            
            return True, f"Database '{db_name}' and tables created successfully"
            
        except Exception as e:
            return False, f"Failed to create database and tables: {str(e)}"
    
    def save_test_cases(self, session_data: Dict[str, Any], test_cases: List[Dict[str, Any]]) -> Tuple[bool, str, Optional[str], int]:
        """
        Save test cases to database.
        
        Args:
            session_data: Session metadata including:
                         - endpoint: API endpoint
                         - method: HTTP method
                         - base_url: Base URL
                         - session_name: Optional session name
                         - created_by: Optional creator name
            test_cases: List of test case dictionaries
            
        Returns:
            Tuple of (success, message, session_id, saved_count)
        """
        if not test_cases:
            return False, "No test cases to save", None, 0
        
        # First, ensure database and tables exist
        success, message = self.test_connection()
        if not success:
            # Try to create database and tables
            success, message = self._create_database_and_tables()
            if not success:
                return False, f"Failed to create database/tables: {message}", None, 0
        
        session_id = str(uuid.uuid4())
        saved_count = 0
        conn = None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Generate table name from base_url, endpoint, and method
            session_name = session_data.get('session_name', f"Test Cases {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            endpoint = session_data.get('endpoint', '/api/test')
            method = session_data.get('method', 'GET')
            base_url = session_data.get('base_url', '')
            created_by = session_data.get('created_by', 'system')
            
            # Generate table name for this endpoint/method combination
            table_name = self._generate_table_name(base_url, endpoint, method)
            print(f"[DEBUG] Generated table name: {table_name}")
            
            # Ensure the table exists
            if not self._ensure_table_exists(table_name, cursor):
                return False, f"Failed to create or verify table '{table_name}'", None, 0
            
            # Filter test cases: only save those matching the frontend values
            filtered_test_cases = []
            for test_case in test_cases:
                # Get values from test case (default to session values if not present)
                tc_endpoint = test_case.get('endpoint', endpoint)
                tc_method = test_case.get('method', method)
                tc_base_url = test_case.get('baseUrl', base_url)
                
                # Check if test case matches the frontend values
                if (tc_endpoint == endpoint and
                    tc_method == method and
                    tc_base_url == base_url):
                    filtered_test_cases.append(test_case)
                else:
                    print(f"[DEBUG] Skipping test case - doesn't match frontend values:")
                    print(f"  Test case: endpoint={tc_endpoint}, method={tc_method}, base_url={tc_base_url}")
                    print(f"  Frontend: endpoint={endpoint}, method={method}, base_url={base_url}")
            
            if not filtered_test_cases:
                return False, "No test cases match the frontend values (base URL, endpoint, method)", None, 0
            
            print(f"[DEBUG] Filtered {len(filtered_test_cases)}/{len(test_cases)} test cases that match frontend values")
            
            # Save session with filtered count
            cursor.execute("""
                INSERT INTO test_case_sessions
                (session_id, session_name, endpoint, http_method, base_url, created_by, total_test_cases, table_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, session_id, session_name, endpoint, method, base_url, created_by, len(filtered_test_cases), table_name)
            
            # Save filtered test cases to the dynamic table
            for i, test_case in enumerate(filtered_test_cases, 1):
                test_case_id = str(uuid.uuid4())
                test_type = test_case.get('type', 'Positive')
                scenario = test_case.get('scenario', '')
                
                # Handle input body (could be dict, list, or string)
                input_body = test_case.get('input', {})
                if isinstance(input_body, (dict, list)):
                    input_body_json = json.dumps(input_body, ensure_ascii=False)
                else:
                    input_body_json = str(input_body)
                
                expected_response = test_case.get('expected', '')
                
                # Extract status codes from expected response (matching Excel logic)
                expected_status_codes = self._extract_response_code(expected_response)
                
                # Extract from test_case if not in session_data
                tc_endpoint = test_case.get('endpoint', endpoint)
                tc_method = test_case.get('method', method)
                tc_base_url = test_case.get('baseUrl', base_url)
                
                metadata = {
                    'id': test_case.get('id', ''),
                    'additional_info': test_case.get('additional_info', {}),
                    'original_table': table_name
                }
                
                # Insert into the dynamic table
                cursor.execute(f"""
                    INSERT INTO [{table_name}]
                    (test_case_id, session_id, test_case_number, test_type, scenario,
                     input_body, expected_response, expected_status_codes,
                     base_url, endpoint, http_method, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, test_case_id, session_id, i, test_type, scenario,
                   input_body_json, expected_response, expected_status_codes,
                   tc_base_url, tc_endpoint, tc_method, json.dumps(metadata))
                
                saved_count += 1
            
            # Commit the transaction
            conn.commit()
            conn.close()
            
            return True, f"Successfully saved {saved_count} test cases to database", session_id, saved_count
            
        except Exception as e:
            # Rollback on error
            try:
                if conn is not None:
                    conn.rollback()
            except:
                pass
            
            error_msg = f"Failed to save test cases: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return False, error_msg, None, saved_count
    
    def get_sessions(self, limit: int = 50, offset: int = 0,
                     endpoint_filter: Optional[str] = None,
                     base_url_filter: Optional[str] = None,
                     method_filter: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        """
        Retrieve saved test case sessions.
        
        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            endpoint_filter: Optional endpoint filter
            base_url_filter: Optional base URL filter
            method_filter: Optional HTTP method filter
            
        Returns:
            Tuple of (sessions list, total count)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            def fetch_scalar() -> int:
                row = cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            
            # Build query with optional filters
            query = """
                SELECT session_id, session_name, endpoint, http_method, base_url,
                       created_by, created_at, total_test_cases, table_name
                FROM test_case_sessions
                WHERE 1=1
            """
            params = []
            
            if endpoint_filter:
                query += " AND endpoint LIKE ?"
                params.append(f"%{endpoint_filter}%")
            
            if base_url_filter:
                query += " AND base_url LIKE ?"
                params.append(f"%{base_url_filter}%")
            
            if method_filter:
                query += " AND http_method = ?"
                params.append(method_filter)
            
            query += " ORDER BY created_at DESC"
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM test_case_sessions WHERE 1=1"
            if endpoint_filter:
                count_query += " AND endpoint LIKE ?"
            if base_url_filter:
                count_query += " AND base_url LIKE ?"
            if method_filter:
                count_query += " AND http_method = ?"
            
            cursor.execute(count_query, params)
            total_count = fetch_scalar()
            
            # Get paginated results
            query += " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
            params.extend([offset, limit])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            sessions = []
            for row in rows:
                session = {
                    'session_id': row.session_id,
                    'session_name': row.session_name,
                    'endpoint': row.endpoint,
                    'method': row.http_method,
                    'base_url': row.base_url,
                    'created_by': row.created_by,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'test_cases_count': row.total_test_cases,
                    'table_name': row.table_name
                }
                sessions.append(session)
            
            conn.close()
            return sessions, total_count
            
        except Exception as e:
            error_msg = f"Failed to retrieve sessions: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return [], 0
    
    def get_test_cases(self, session_id: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Retrieve test cases for a specific session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Tuple of (session_info, test_cases list)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Get session info including table_name
            cursor.execute("""
                SELECT session_id, session_name, endpoint, http_method, base_url,
                       created_by, created_at, total_test_cases, table_name
                FROM test_case_sessions
                WHERE session_id = ?
            """, session_id)
            
            session_row = cursor.fetchone()
            if not session_row:
                conn.close()
                return None, []
            
            table_name = session_row.table_name
            session_info = {
                'session_id': session_row.session_id,
                'session_name': session_row.session_name,
                'endpoint': session_row.endpoint,
                'http_method': session_row.http_method,
                'base_url': session_row.base_url,
                'created_by': session_row.created_by,
                'created_at': session_row.created_at.isoformat() if session_row.created_at else None,
                'total_test_cases': session_row.total_test_cases,
                'table_name': table_name
            }
            
            # Get test cases from the dynamic table
            cursor.execute(f"""
                SELECT test_case_id, test_case_number, test_type, scenario,
                       input_body, expected_response, expected_status_codes,
                       base_url, endpoint, http_method, metadata, created_at
                FROM [{table_name}]
                WHERE session_id = ?
                ORDER BY test_case_number
            """, session_id)
            
            rows = cursor.fetchall()
            test_cases = []
            
            for row in rows:
                # Parse input body JSON if possible
                input_body = row.input_body
                try:
                    if input_body and input_body.strip():
                        input_body = json.loads(input_body)
                except:
                    pass  # Keep as string if not valid JSON
                
                # Parse metadata JSON
                metadata = {}
                if row.metadata and row.metadata.strip():
                    try:
                        metadata = json.loads(row.metadata)
                    except:
                        pass
                
                test_case = {
                    'id': row.test_case_id,  # Map to 'id' for compatibility with execution logic
                    'test_case_id': row.test_case_id,
                    'test_case_number': row.test_case_number,
                    'type': row.test_type,
                    'scenario': row.scenario,
                    'input': input_body,
                    'expected': row.expected_response,
                    'expected_status': row.expected_status_codes,
                    'baseUrl': row.base_url,
                    'endpoint': row.endpoint,
                    'method': row.http_method,
                    'metadata': metadata,
                    'created_at': row.created_at.isoformat() if row.created_at else None
                }
                test_cases.append(test_case)
            
            conn.close()
            return session_info, test_cases
            
        except Exception as e:
            error_msg = f"Failed to retrieve test cases: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return None, []


# Global database instance
db_instance = None


def get_database() -> TestCaseDatabase:
    """
    Get or create global database instance.
    
    Returns:
        TestCaseDatabase instance
    """
    global db_instance
    if db_instance is None:
        db_instance = TestCaseDatabase()
    return db_instance


def initialize_database() -> Tuple[bool, str]:
    """
    Initialize database connection and test.
    
    Returns:
        Tuple of (success, message)
    """
    try:
        db = get_database()
        return db.test_connection()
    except Exception as e:
        return False, f"Database initialization failed: {str(e)}"