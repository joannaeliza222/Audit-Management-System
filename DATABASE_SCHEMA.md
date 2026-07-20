# Database Schema Documentation

## Overview

The AMS uses PostgreSQL with the pgvector extension for vector embeddings. The database is organized into several main tables for query management, user authentication, document processing, and audit tracking.

## Core Tables

### users

User accounts with role-based access control.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique user identifier |
| name | String(50) | nullable | User's full name |
| email | String(120) | UNIQUE, NOT NULL | User's email address (login identifier) |
| password | String(200) | NOT NULL | Argon2id hashed password |
| role | String(20) | nullable | User role: admin, reviewer, modifier, viewer |
| state_name | String(100) | nullable | State/region assignment |
| is_approved | Boolean | DEFAULT: False | Account approval status |
| email_verified | Boolean | DEFAULT: False | Email verification status |
| email_verification_token | String(100) | nullable, INDEX | Token for email verification |
| password_reset_token | String(100) | nullable, INDEX | Token for password reset |
| password_reset_expires | DateTime | nullable | Password reset token expiration |

**Indexes**: email (unique), email_verification_token, password_reset_token

---

### faq

Approved frequently asked questions and responses.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique FAQ identifier |
| subject | String(500) | NOT NULL | Subject/title of the query |
| query_description | Text | NOT NULL | Detailed query description |
| norm_query | String(1024) | NOT NULL, INDEX | Normalized lowercase query for uniqueness |
| reply | Text | nullable | Response/answer to the query |
| memo_id | String(128) | nullable | Optional memo/reference ID |
| state_name | String(100) | nullable, INDEX | State name for query separation |
| query_date | Date | nullable | Date when query was created |
| timestamp | DateTime | DEFAULT: utcnow() | Timestamp when FAQ was added |
| embedding | LargeBinary | nullable | Vector embedding (384-dim) for semantic search |

**Indexes**: norm_query, state_name
**Unique Constraint**: uq_query_state (norm_query, state_name)

---

### draftfaq

Draft FAQ entries awaiting review and approval.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique draft identifier |
| original_id | Integer | FOREIGN KEY → faq.id, nullable | Reference to merged FAQ |
| subject | String(500) | NOT NULL | Subject/title of the query |
| query_description | Text | NOT NULL | Detailed query description |
| norm_query | String(1024) | NOT NULL, INDEX | Normalized lowercase query |
| reply | Text | nullable | Draft response |
| memo_id | String(128) | nullable | Optional memo/reference ID |
| state_name | String(100) | nullable, INDEX | State name for query separation |
| query_date | Date | nullable | Date when query was created |
| status | Enum | NOT NULL, INDEX | pending, admin_draft, merged, rejected |
| created_by | String(120) | nullable | User who created the draft |
| modified_by | String(120) | nullable | User who modified the reply |
| approved_by | String(120) | nullable | User who merged the draft |
| created_at | DateTime | DEFAULT: utcnow() | Draft creation timestamp |
| modified_at | DateTime | nullable | Last modification timestamp |
| approved_at | DateTime | nullable | Approval timestamp |
| embedding | LargeBinary | nullable | Vector embedding for semantic search |

**Indexes**: norm_query, state_name, status
**Unique Constraint**: uq_draft_query_state (norm_query, state_name)
**Relationships**: 
- original_id → faq.id (SET NULL)
- future_issues (one-to-many, CASCADE delete)

---

### future_issue_tracker

Tracking of potential issues that may arise from query responses.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique issue identifier |
| related_draft_id | Integer | FOREIGN KEY → draftfaq.id, nullable | Related draft FAQ |
| related_faq_id | Integer | FOREIGN KEY → faq.id, nullable | Related approved FAQ |
| description | Text | NOT NULL | Issue description |
| detected_at | DateTime | DEFAULT: utcnow() | When issue was detected |
| status | String(50) | DEFAULT: 'not addressed' | Issue status |
| version_detected | String(50) | nullable | Version where issue was found |
| version_fixed | String(50) | nullable | Version where issue was fixed |
| note | Text | nullable | Additional notes |

**Relationships**:
- related_draft_id → draftfaq.id (CASCADE)
- related_faq_id → faq.id (SET NULL)

---

### data_dump

Management of data dump requests and file sharing.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique data dump identifier |
| state | String(100) | NOT NULL | State requesting data dump |
| nodal_dept | String(200) | nullable | Nodal department name |
| request_date | Date | nullable | Date request was mailed |
| coordinator | String(200) | nullable | Coordinator's email |
| request_email | Text | nullable | Description of data needed |
| file_name | String(200) | nullable | Name of shared file |
| md5_hash | String(200) | nullable | MD5 hash of shared file |
| file_size | String(50) | nullable | Size of the file |
| period_shared | String(50) | nullable | Period covered by data |
| postgres_version | String(100) | nullable | PostgreSQL version of backup |
| command_to_restore | Text | nullable | Command to restore backup |
| db_size | String(50) | nullable | Expected database size |
| share_date | Date | nullable | Date data was shared |
| share_mode | String(200) | nullable | Mode of sharing |
| coordinator_name | String(200) | nullable | Coordinator's name |
| share_link | String(500) | nullable | Download link |
| shared_to | String(200) | nullable | Recipient |
| file_path | String(1000) | nullable | File storage path |
| is_file_available | Boolean | DEFAULT: False | File availability status |
| download_token | String(100) | UNIQUE, INDEX | Secure download token |
| status | String(20) | DEFAULT: 'requested' | requested, provided, rejected, acknowledged |
| remarks | Text | nullable | Additional remarks |
| created_at | DateTime | DEFAULT: utcnow() | Request creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE | Last update timestamp |
| generated_doc | String(200) | nullable | Generated document path |
| user_uploaded_doc | String(200) | nullable | User uploaded document path |
| user_doc_signed | Boolean | DEFAULT: False | Document signed status |
| user_doc_verified | Boolean | DEFAULT: False | Document verification status |
| user_doc_downloaded | Boolean | DEFAULT: False | Document download status |

**Indexes**: download_token

---

### failed_login_attempts

Tracking of failed login attempts for security.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique attempt identifier |
| email | String(120) | NOT NULL, INDEX | Email address used |
| ip_address | String(45) | nullable | IP address of attempt |
| attempt_time | DateTime | DEFAULT: utcnow(), INDEX | Timestamp of attempt |
| success | Boolean | DEFAULT: False | Whether attempt succeeded |

**Indexes**: email, attempt_time

---

### notifications

User notifications for system events.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique notification identifier |
| user_email | String(120) | NOT NULL, INDEX | Recipient email |
| title | String(200) | NOT NULL | Notification title |
| message | Text | NOT NULL | Notification message |
| notification_type | String(50) | DEFAULT: 'info' | info, warning, success, error |
| related_draft_id | Integer | FOREIGN KEY → draftfaq.id, nullable | Related draft |
| related_faq_id | Integer | FOREIGN KEY → faq.id, nullable | Related FAQ |
| related_issue_id | Integer | FOREIGN KEY → future_issue_tracker.id, nullable | Related issue |
| is_read | Boolean | DEFAULT: False, INDEX | Read status |
| created_at | DateTime | DEFAULT: utcnow(), INDEX | Creation timestamp |
| read_at | DateTime | nullable | Read timestamp |

**Indexes**: user_email, is_read, created_at

---

## Audit Management Tables

### audit_query

Main audit query tracking table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique query identifier |
| query_id | String(50) | UNIQUE, NOT NULL, INDEX | External query identifier |
| state_name | String(100) | NOT NULL, INDEX | State name |
| date_received | Date | NOT NULL, INDEX | Date query was received |
| query_description | Text | NOT NULL | Query details |
| assigned_official | String(200) | nullable | Assigned official name |
| assigned_official_email | String(120) | nullable | Assigned official email |
| department | String(200) | nullable | Department name |
| priority | String(20) | DEFAULT: 'medium' | low, medium, high, critical |
| status | Enum | NOT NULL, INDEX | received, in_progress, awaiting_response, responded, closed, escalated |
| response_provided | Text | nullable | Response content |
| response_date | Date | nullable | Response date |
| response_method | String(50) | nullable | email, letter, portal |
| source_document | String(500) | nullable | Original document path |
| memo_id | String(128) | nullable, INDEX | Memo reference |
| audit_year | Integer | nullable, INDEX | Audit year |
| audit_type | String(100) | nullable | financial, compliance, performance |
| embedding | LargeBinary | nullable | Vector embedding (384-dim) |
| created_at | DateTime | DEFAULT: utcnow() | Creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE | Last update timestamp |
| closed_at | DateTime | nullable | Closure timestamp |

**Indexes**: query_id, state_name, date_received, status, memo_id, audit_year
**Relationships**:
- commitments (one-to-many, CASCADE delete)
- version_history (one-to-many, CASCADE delete)

---

### commitment

Commitments extracted from audit query responses.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique commitment identifier |
| audit_query_id | Integer | FOREIGN KEY → audit_query.id, NOT NULL | Parent query |
| commitment_text | Text | NOT NULL | Commitment description |
| commitment_type | String(50) | nullable | rectification, implementation, policy_change |
| target_date | Date | nullable, INDEX | Target completion date |
| status | Enum | NOT NULL, INDEX | pending, in_progress, completed, overdue, cancelled |
| detected_at | DateTime | DEFAULT: utcnow() | Detection timestamp |
| completed_at | DateTime | nullable | Completion timestamp |
| overdue_notified | Boolean | DEFAULT: False | Overdue notification sent |
| responsible_party | String(200) | nullable | Responsible person/department |
| implementation_notes | Text | nullable | Implementation details |
| verification_method | String(200) | nullable | How to verify completion |
| created_at | DateTime | DEFAULT: utcnow() | Creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE | Last update timestamp |

**Indexes**: target_date, status
**Relationships**: audit_query_id → audit_query.id (CASCADE)

---

### query_version

Version history for audit queries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique version identifier |
| audit_query_id | Integer | FOREIGN KEY → audit_query.id, NOT NULL | Parent query |
| version_number | Integer | NOT NULL | Version sequence number |
| change_type | String(50) | NOT NULL | created, response_updated, status_changed, reassigned |
| previous_status | Enum | nullable | Previous status value |
| new_status | Enum | nullable | New status value |
| previous_response | Text | nullable | Previous response content |
| new_response | Text | nullable | New response content |
| previous_assigned | String(200) | nullable | Previous assignee |
| new_assigned | String(200) | nullable | New assignee |
| changed_by | String(120) | NOT NULL | User who made change |
| change_reason | Text | nullable | Reason for change |
| change_timestamp | DateTime | DEFAULT: utcnow(), INDEX | When change occurred |
| full_snapshot | JSON | nullable | Complete record snapshot |

**Indexes**: change_timestamp
**Relationships**: audit_query_id → audit_query.id (CASCADE)

---

### document_processing

Document processing tracking for query extraction.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique processing identifier |
| original_filename | String(500) | NOT NULL | Original file name |
| stored_filename | String(500) | NOT NULL | Stored file name |
| file_path | String(1000) | NOT NULL | File storage path |
| file_type | String(10) | NOT NULL | pdf, xlsx, csv |
| file_size | BigInteger | NOT NULL | Size in bytes |
| mime_type | String(100) | NOT NULL | MIME type |
| checksum | String(64) | NOT NULL, INDEX | File checksum (SHA-256) |
| processing_status | String(50) | DEFAULT: 'pending' | pending, processing, completed, failed |
| processing_started | DateTime | nullable | Processing start time |
| processing_completed | DateTime | nullable | Processing completion time |
| processing_error | Text | nullable | Error message if failed |
| extracted_queries | Integer | DEFAULT: 0 | Number of queries extracted |
| extracted_qa_pairs | Integer | DEFAULT: 0 | Number of Q&A pairs extracted |
| extraction_confidence | Float | nullable | Extraction confidence score |
| uploaded_by | String(120) | NOT NULL | User who uploaded |
| upload_timestamp | DateTime | DEFAULT: utcnow() | Upload timestamp |

**Indexes**: checksum
**Relationships**: extracted_items (one-to-many, CASCADE delete)

---

### extracted_item

Items extracted from documents.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique item identifier |
| document_id | Integer | FOREIGN KEY → document_processing.id, NOT NULL | Parent document |
| item_type | String(20) | NOT NULL | question, answer, qa_pair, statement |
| content | Text | NOT NULL | Extracted content |
| confidence_score | Float | nullable | Extraction confidence |
| page_number | Integer | nullable | Page number in document |
| bounding_box | JSON | nullable | Text coordinates (x, y, width, height) |
| text_context | Text | nullable | Surrounding text context |
| processed_to_query | Boolean | DEFAULT: False | Converted to query |
| audit_query_id | Integer | FOREIGN KEY → audit_query.id, nullable | Linked query |
| processing_notes | Text | nullable | Processing notes |
| extracted_at | DateTime | DEFAULT: utcnow() | Extraction timestamp |
| processed_at | DateTime | nullable | Processing timestamp |

**Relationships**: document_id → document_processing.id (CASCADE), audit_query_id → audit_query.id (SET NULL)

---

## Document Q&A Tables

### secure_documents

Secure document storage with user isolation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique document identifier |
| user_id | Integer | FOREIGN KEY → user.id, NOT NULL, INDEX | Document owner |
| original_filename | String(255) | NOT NULL | Original file name |
| stored_filename | String(255) | UNIQUE, NOT NULL | UUID-based filename |
| file_path | String(1000) | NOT NULL | File storage path |
| file_size | Integer | NOT NULL | Size in bytes |
| mime_type | String(100) | NOT NULL | MIME type |
| file_hash | String(64) | NOT NULL, INDEX | SHA-256 hash |
| status | Enum | NOT NULL, INDEX | uploading, processing, ready, failed, deleted |
| processing_error | Text | nullable | Error message |
| processing_started_at | DateTime | nullable | Processing start |
| processing_completed_at | DateTime | nullable | Processing completion |
| access_level | Enum | NOT NULL | private, shared |
| is_encrypted | Boolean | DEFAULT: True, NOT NULL | Encryption status |
| encryption_key_hash | String(64) | nullable | Hash of encryption key |
| page_count | Integer | nullable | Number of pages |
| word_count | Integer | nullable | Word count |
| extracted_text_length | Integer | nullable | Extracted text length |
| created_at | DateTime | DEFAULT: utcnow(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE, NOT NULL | Last update timestamp |
| deleted_at | DateTime | nullable | Soft delete timestamp |

**Indexes**: user_id, status, file_hash, created_at
**Composite Indexes**: idx_document_user_status (user_id, status), idx_document_created_at (created_at), idx_document_file_hash (file_hash)
**Relationships**: 
- user → User.id (CASCADE delete)
- chunks (one-to-many, CASCADE delete)
- qa_sessions (one-to-many, CASCADE delete)

---

### qa_document_chunks

Document chunks for Q&A vector search.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique chunk identifier |
| document_id | Integer | FOREIGN KEY → secure_documents.id, NOT NULL, INDEX | Parent document |
| user_id | Integer | FOREIGN KEY → user.id, NOT NULL, INDEX | Document owner |
| chunk_text | Text | NOT NULL | Chunk content |
| chunk_index | Integer | NOT NULL | Order within document |
| page_number | Integer | nullable | Page number |
| embedding | Vector(384) | NOT NULL | pgvector embedding |
| chunk_type | String(50) | DEFAULT: 'text', NOT NULL | text, table, image_caption |
| confidence_score | Float | nullable | OCR confidence |
| created_at | DateTime | DEFAULT: utcnow(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE, NOT NULL | Last update timestamp |

**Indexes**: document_id, user_id
**Composite Indexes**: idx_qa_chunk_document_user (document_id, user_id), idx_qa_chunk_index (document_id, chunk_index)
**Relationships**: user → User.id (CASCADE delete)

---

### qa_sessions

Q&A session management for documents.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique session identifier |
| document_id | Integer | FOREIGN KEY → secure_documents.id, NOT NULL, INDEX | Associated document |
| user_id | Integer | FOREIGN KEY → user.id, NOT NULL, INDEX | Session owner |
| session_name | String(255) | nullable | Session name |
| session_token | String(64) | UNIQUE, NOT NULL, INDEX | Secure session token |
| question_count | Integer | DEFAULT: 0, NOT NULL | Number of questions |
| last_activity_at | DateTime | DEFAULT: utcnow(), NOT NULL | Last activity timestamp |
| created_at | DateTime | DEFAULT: utcnow(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE, NOT NULL | Last update timestamp |

**Indexes**: document_id, user_id, session_token, last_activity_at
**Composite Indexes**: idx_session_document_user (document_id, user_id), idx_session_token (session_token), idx_session_last_activity (last_activity_at)
**Relationships**: 
- user → User.id (CASCADE delete)
- conversations (one-to-many, CASCADE delete)

---

### qa_conversations

Individual Q&A conversations within sessions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique conversation identifier |
| session_id | Integer | FOREIGN KEY → qa_sessions.id, NOT NULL, INDEX | Parent session |
| user_id | Integer | FOREIGN KEY → user.id, NOT NULL, INDEX | Conversation owner |
| question | Text | NOT NULL | User question |
| question_embedding | Vector(384) | NOT NULL | Question embedding |
| answer | Text | NOT NULL | AI-generated answer |
| answer_sources | Text | nullable | JSON of source chunks |
| confidence_score | Float | nullable | Answer confidence |
| response_time_ms | Integer | nullable | Response time in milliseconds |
| model_used | String(100) | nullable | LLM model used |
| relevant_chunks | Text | nullable | JSON of chunk IDs |
| context_length | Integer | nullable | Context character count |
| created_at | DateTime | DEFAULT: utcnow(), NOT NULL | Creation timestamp |

**Indexes**: session_id, user_id, created_at
**Composite Indexes**: idx_conversation_session_user (session_id, user_id), idx_conversation_created_at (created_at)
**Relationships**: user → User.id (CASCADE delete)

---

### document_access_logs

Audit log for document access.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique log identifier |
| document_id | Integer | FOREIGN KEY → secure_documents.id, NOT NULL, INDEX | Accessed document |
| user_id | Integer | FOREIGN KEY → user.id, NOT NULL, INDEX | Accessing user |
| action | String(50) | NOT NULL | upload, view, download, delete, query |
| ip_address | String(45) | nullable | IP address |
| user_agent | Text | nullable | User agent string |
| session_id | String(64) | nullable | Session identifier |
| additional_data | Text | nullable | JSON of additional context |
| created_at | DateTime | DEFAULT: utcnow(), NOT NULL | Access timestamp |

**Indexes**: document_id, user_id, action, created_at
**Composite Indexes**: idx_access_document_user (document_id, user_id), idx_access_action (action), idx_access_created_at (created_at)
**Relationships**: 
- user → User.id (CASCADE delete)
- document → SecureDocument.id (CASCADE delete)

---

### document_shares

Document sharing between users.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PRIMARY KEY | Unique share identifier |
| document_id | Integer | FOREIGN KEY → secure_documents.id, NOT NULL, INDEX | Shared document |
| shared_by_user_id | Integer | FOREIGN KEY → user.id, NOT NULL, INDEX | Sharer |
| shared_with_user_id | Integer | FOREIGN KEY → user.id, nullable | Recipient |
| share_token | String(64) | UNIQUE, NOT NULL, INDEX | Secure share token |
| permission_level | String(20) | DEFAULT: 'view', NOT NULL | view, query |
| expires_at | DateTime | nullable | Expiration timestamp |
| max_queries | Integer | nullable | Maximum query count |
| query_count | Integer | DEFAULT: 0, NOT NULL | Current query count |
| is_active | Boolean | DEFAULT: True, NOT NULL | Active status |
| revoked_at | DateTime | nullable | Revocation timestamp |
| created_at | DateTime | DEFAULT: utcnow(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT: utcnow(), ON UPDATE, NOT NULL | Last update timestamp |

**Indexes**: document_id, shared_by_user_id, share_token
**Composite Indexes**: idx_share_document_shared_by (document_id, shared_by_user_id), idx_share_token (share_token), idx_share_active (is_active, expires_at)
**Relationships**: 
- shared_by_user → User.id (CASCADE delete)
- shared_with_user → User.id (CASCADE delete)
- document → SecureDocument.id (CASCADE delete)

---

## Database Extensions

### pgvector

Required for vector embeddings and semantic search functionality.

- **Installation**: `CREATE EXTENSION IF NOT EXISTS vector;`
- **Usage**: Stores 384-dimensional embeddings from Sentence Transformers model
- **Tables using pgvector**: qa_document_chunks, qa_conversations

---

## Relationships Summary

```
User (1) ──< (N) DraftFAQ ──< (N) FutureIssueTracker
User (1) ──< (N) SecureDocument ──< (N) QADocumentChunk
User (1) ──< (N) QASession ──< (N) QAConversation
User (1) ──< (N) DocumentAccessLog
User (1) ──< (N) DocumentShare (as shared_by_user_id)
User (1) ──< (N) DocumentShare (as shared_with_user_id)

FAQ (1) ──< (N) DraftFAQ (via original_id)
FAQ (1) ──< (N) FutureIssueTracker (via related_faq_id)
FAQ (1) ──< (N) Notification (via related_faq_id)

DraftFAQ (1) ──< (N) FutureIssueTracker (via related_draft_id)
DraftFAQ (1) ──< (N) Notification (via related_draft_id)

AuditQuery (1) ──< (N) Commitment
AuditQuery (1) ──< (N) QueryVersion
DocumentProcessing (1) ──< (N) ExtractedItem
```

---

## Security Considerations

1. **Password Storage**: All passwords are hashed using Argon2id with memory-hard parameters
2. **Document Encryption**: Documents are encrypted using Fernet symmetric encryption
3. **Audit Logging**: All sensitive operations are logged in document_access_logs
4. **Row-Level Security**: Document Q&A tables include user_id for data isolation
5. **Soft Deletes**: Secure documents use soft delete (deleted_at) for data retention
6. **Token Security**: Download tokens and session tokens use SHA-256 hashing

---

## Migration Notes

- Use Flask-Migrate (Alembic) for schema changes
- Always test migrations in staging before production
- Backup database before running migrations
- Document breaking changes in migration files
