# Database Saving Implementation Plan for API Test Command Center

## Overview
This plan outlines the implementation of database saving functionality for the API Test Command Center. When users click the "Export" button, they will see an alert with two options: "Save to Local" (existing Excel download) and "Save to Database". If they choose "Save to Database", test cases will be saved to a SQL Server database with the provided credentials.

## Database Configuration
- **Server Name**: LPT2149-B1
- **User Name**: testUser1
- **Password**: TestUser@1
- **Database Name**: API_Test_Cases (to be created)
- **Driver**: ODBC Driver 17 for SQL Server

## Implementation Phases

### Phase 1: Database Setup
1. **Install Required Dependencies**
   - Add `pyodbc>=4.0.39` to `requirements.txt`
   - Install: `pip install pyodbc`

2. **Create Database and Tables**
   - Connect to SQL Server using provided credentials
   - Create `API_Test_Cases` database
   - Execute SQL scripts to create tables:
     - `test_case_sessions` (stores export sessions)
     - `test_cases` (stores individual test cases)
     - `execution_logs` (optional, for future execution tracking)

3. **Test Database Connection**
   - Create a test script to verify connectivity
   - Validate credentials and permissions

### Phase 2: Backend Implementation
1. **Create Database Connection Module**
   - File: `database.py`
   - Class: `TestCaseDatabase` with methods for connection, saving, and retrieval
   - Connection string configuration using environment variables

2. **Add New API Endpoints to `app.py`**
   - `POST /api/save-to-database`: Save generated test cases to database
   - `GET /api/database-sessions`: Retrieve saved sessions
   - `GET /api/database-test-cases/<session_id>`: Get test cases for a session

3. **Integrate with Existing Test Case Generation**
   - Reuse the same test case generation logic from `/api/export-excel`
   - Add session metadata (timestamp, user, endpoint, method)
   - Implement transaction handling for reliable saves

### Phase 3: Frontend Implementation
1. **Add Export Modal to `templates/index.html`**
   - Create modal HTML with two options: "Save to Local" and "Save to Database"
   - Style modal to match existing UI design
   - Add close/cancel functionality

2. **Update JavaScript Functions**
   - Replace `downloadExcel()` with `showExportOptions()`
   - Implement `saveToLocal()` (calls existing Excel export)
   - Implement `saveToDatabase()` (calls new API endpoint)
   - Add loading states and user feedback

3. **Enhance User Feedback**
   - Success notifications with session ID and count
   - Error handling with specific messages
   - Loading indicators during database operations

### Phase 4: Testing & Validation
1. **Database Connection Testing**
   - Test with valid/invalid credentials
   - Test network connectivity to server
   - Test with large datasets

2. **API Endpoint Testing**
   - Test `/api/save-to-database` with various payloads
   - Test retrieval endpoints
   - Test error scenarios

3. **Integration Testing**
   - Test complete flow: Generate → Export → Save to DB → Retrieve
   - Test concurrent exports
   - Test with different HTTP methods and payload types

4. **User Interface Testing**
   - Test modal appearance and behavior
   - Test responsive design
   - Test accessibility

## Detailed Technical Specifications

### Database Schema

#### Table: test_case_sessions
```sql
CREATE TABLE test_case_sessions (
    session_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    session_name NVARCHAR(255),
    endpoint NVARCHAR(500),
    http_method NVARCHAR(10),
    base_url NVARCHAR(500),
    created_by NVARCHAR(100) DEFAULT 'system',
    created_at DATETIME DEFAULT GETDATE(),
    total_test_cases INT DEFAULT 0
)
```

#### Table: test_cases
```sql
CREATE TABLE test_cases (
    test_case_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    session_id UNIQUEIDENTIFIER FOREIGN KEY REFERENCES test_case_sessions(session_id),
    test_case_number INT,
    test_type NVARCHAR(50), -- 'Positive', 'Negative', 'Security', 'Performance', etc.
    scenario NVARCHAR(1000),
    input_body NVARCHAR(MAX),
    expected_response NVARCHAR(1000),
    expected_status_codes NVARCHAR(100), -- comma-separated codes
    base_url NVARCHAR(500),
    endpoint NVARCHAR(500),
    http_method NVARCHAR(10),
    created_at DATETIME DEFAULT GETDATE(),
    metadata NVARCHAR(MAX) -- JSON for additional fields
)
```

### API Endpoint Specifications

#### POST /api/save-to-database
**Request Body**: Same as `/api/export-excel`
```json
{
  "method": "POST",
  "endpoint": "/api/users",
  "payload": "{\"name\": \"test\"}",
  "field_configs": {...},
  "baseUrl": "https://api.example.com"
}
```

**Response**:
```json
{
  "success": true,
  "session_id": "uuid-string",
  "message": "Saved 15 test cases to database",
  "saved_count": 15
}
```

### Frontend Modal Design
```html
<div id="exportModal" class="modal" style="display: none;">
    <div class="modal-content">
        <h3>Export Test Cases</h3>
        <p>Choose how you want to save the generated test cases:</p>
        <div class="export-options">
            <button class="btn btn-secondary" onclick="saveToLocal()">
                <i data-lucide="download"></i> Save to Local (Excel)
            </button>
            <button class="btn btn-primary" onclick="saveToDatabase()">
                <i data-lucide="database"></i> Save to Database
            </button>
            <button class="btn btn-outline" onclick="closeExportModal()">Cancel</button>
        </div>
    </div>
</div>
```

## Files to Modify

### New Files
1. `database.py` - Database connection and operations
2. `database_schema.sql` - SQL scripts for table creation
3. `test_database.py` - Unit tests for database operations

### Modified Files
1. `app.py` - Add new API endpoints
2. `templates/index.html` - Add export modal and update button
3. `requirements.txt` - Add pyodbc dependency
4. `static/js/main.js` (if exists) or inline JavaScript in index.html - Update export functions

## Error Handling Strategy

### Database Errors
- Connection failures: Fall back to local save with warning
- Timeout errors: Retry logic with exponential backoff
- Permission errors: Clear user-friendly message

### User Input Errors
- Invalid test cases: Validate before saving
- Missing required fields: Provide specific feedback
- Large datasets: Implement pagination or batch processing

### Network Errors
- API call failures: Retry with user confirmation
- Server unavailable: Cache and retry later

## Security Considerations

1. **Credential Management**
   - Store database password in environment variables
   - Never hardcode credentials in source files
   - Use Azure Key Vault or similar for production

2. **SQL Injection Prevention**
   - Use parameterized queries exclusively
   - Validate all inputs before database operations
   - Implement proper escaping for dynamic SQL

3. **Data Privacy**
   - Consider masking sensitive data in test cases
   - Implement access controls for database
   - Regular security audits

## Performance Considerations

1. **Connection Pooling**
   - Implement connection pooling for database connections
   - Reuse connections across requests
   - Set appropriate timeout values

2. **Batch Operations**
   - Save test cases in batches (e.g., 100 at a time)
   - Use bulk insert operations for large datasets
   - Implement asynchronous saving for better UX

3. **Caching**
   - Cache frequently accessed sessions
   - Implement query optimization for retrieval

## Deployment Checklist

- [ ] Database created and tables initialized
- [ ] pyodbc installed on server
- [ ] Environment variables configured
- [ ] API endpoints tested
- [ ] Frontend changes deployed
- [ ] User documentation updated
- [ ] Backup strategy implemented

## Success Metrics

1. **Functionality**
   - Users can successfully save test cases to database
   - Saved test cases can be retrieved accurately
   - Error handling provides clear feedback

2. **Performance**
   - Database save completes within 5 seconds for 100 test cases
   - Retrieval of sessions is near-instant
   - No impact on existing Excel export functionality

3. **Usability**
   - Users understand the two export options
   - Modal interface is intuitive
   - Success/error messages are clear

## Rollback Plan

If issues arise during deployment:
1. Revert frontend changes to restore original export button
2. Disable new API endpoints
3. Remove pyodbc dependency if causing issues
4. Restore from backup if database changes caused problems

## Timeline Estimate

- **Phase 1 (Database Setup)**: 1 day
- **Phase 2 (Backend Implementation)**: 2 days
- **Phase 3 (Frontend Implementation)**: 1 day
- **Phase 4 (Testing & Validation)**: 1 day
- **Total**: 5 business days

## Next Steps

1. Review this plan with stakeholders
2. Set up development environment with database access
3. Begin implementation with Phase 1
4. Regular progress reviews and testing
5. Final deployment and user training

---

*Last Updated: 2026-04-13*  
*Version: 1.0*  
*Author: Implementation Planning Team*