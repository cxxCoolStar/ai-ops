# AI-Ops Bug Fix Library Visualization & Debugging Tool PRD

## 1. Project Background
AI-Ops is an agentic auto-repair system. As it processes various repository errors, it builds a "Bug Fix Library" consisting of historical bug cases and their corresponding fixes (revisions). To improve the system's transparency and allow developers to tune the retrieval logic, a visualization and debugging interface is required.

## 2. Product Goals
- **Visibility**: Provide a clear view of all bug cases stored in the system.
- **Traceability**: Track the execution history of auto-repair tasks (Traces).
- **Debuggability**: Allow developers to manually test the feature extraction and similarity search logic using real or simulated log traces.
- **Maintenance**: Facilitate the review of "Quality Scores" and revisions for each bug case.

## 3. Target Users
- **AI-Ops Core Developers**: Tuning algorithms and debugging retrieval failures.
- **System Operators**: Monitoring the health and performance of the auto-repair pipeline.

## 4. Requirement Description

### 4.1 Bug Fix Library (Case Management)
- **Grid/List View**: Display bug cases with key metadata aligned with `TraceStore` schema:
  - **Exception Type** (e.g., `ValueError`, `TypeError`).
  - **Message Key** (Human-readable error summary).
  - **Signature** (SHA-256 fingerprint, truncated in list, full in detail).
  - **Repository Name** (Extracted from `repo_url`).
  - **Quality Score** (Numerical confidence metric).
  - **Updated Date**.
- **Search & Filter**: Search cases by Signature hash, Exception type, or Message content.
- **Case Detail Modal**:
  - Full **Signature** and **Repo URL** (Clickable).
  - **Code Host** (e.g., `github.com`).
  - **Top Stack Frames** (Formatted list).
  - **Revision History** (PR/Commit links and fix counts).

### 4.2 Call History (Trace Management)
- **Execution Log**: A table showing all system repair attempts (Trace ID, Repo, Status, Time).
- **Status Tracking**: Visual indicators (Neon Badges) for `DONE`, `RUNNING`, and `FAILED` states.
- **Retrieval Context**: Expandable details for each trace:
  - **Log Query**: The original traceback/log input.
  - **Top Match**: The best matching case identified from the library.
- **History-to-Debug Linkage**: One-click "Debug" button to pre-fill the Debugger with historical data.

### 4.3 Retrieval Debugger (Internal Tool)
- **Simulated Input**: A text area for pasting traceback logs.
- **Feature Extraction**: Real-time display of Extraction results:
  - Extracted Exception Type.
  - Calculated Signature Hash.
  - Normalized Query Text.
- **Match Strategy Verification**: List top potential matches with quality scores.

## 5. User Interface (UI) Design
- **Aesthetic**: Modern "Cyberpunk/Dark Mode" theme.
  - Primary Color: `#9b51e0` (Purple).
  - Secondary Color: `#00f2fe` (Teal).
- **Layout**: Single Page Application (SPA) with sticky top navigation.
- **Components**: Glassmorphism cards, blurred backgrounds, and micro-animations.

## 6. Technology Stack
- **Frontend Framework**: **React 18** (distributed via CDN for Zero-Build deployment).
- **State Management**: React Hooks (`useState`, `useMemo`, `useEffect`).
- **Styling**: Vanilla CSS with HSL variables and CSS Animations.
- **Environment**: Integrated with Python `http_server.py`.

## 7. Technical Architecture & API
- **Data Source**: `TraceStore` subclassing SQLite.
- **Endpoint Specifications**:
  - `GET /v1/bug-cases`: paginated case list.
  - `GET /v1/bug-cases/{id}`: full revision details.
  - `GET /v1/traces`: recent task history.
  - `POST /v1/debug/retrieval`: simulation endpoint.

## 8. Data Alignment
The implementation strictly follows the `TraceStore._init_db` schema, ensuring `case_id`, `repo_url`, `code_host`, `signature`, and `quality_score` are correctly mapped between the SQLite storage and the React UI.
