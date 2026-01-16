const { useState, useEffect } = React;

const App = () => {
    const [view, setView] = useState('library');
    const [searchQuery, setSearchQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [debugInput, setDebugInput] = useState('');
    const [debugResult, setDebugResult] = useState(null);
    const [selectedCase, setSelectedCase] = useState(null);
    const [cases, setCases] = useState([]);
    const [traces, setTraces] = useState([]);
    const [casePaging, setCasePaging] = useState({ limit: 50, offset: 0, total: 0 });
    const [tracePaging, setTracePaging] = useState({ limit: 50, offset: 0, total: 0 });

    const fetchCases = async () => {
        try {
            const params = new URLSearchParams();
            params.set('limit', casePaging.limit);
            params.set('offset', casePaging.offset);
            if (searchQuery.trim()) params.set('q', searchQuery.trim());
            const res = await fetch(`/v1/bug-cases?${params.toString()}`);
            const data = await res.json();
            const items = Array.isArray(data) ? data : (data.items || []);
            setCases(items);
            if (!Array.isArray(data)) {
                setCasePaging(p => ({ ...p, limit: data.limit || p.limit, offset: data.offset || p.offset, total: data.total || 0 }));
            } else {
                setCasePaging(p => ({ ...p, offset: 0, total: items.length }));
            }
        } catch (e) {
            console.error('Error fetching cases:', e);
            setCases([]);
        }
    };

    const fetchTraces = async () => {
        try {
            const params = new URLSearchParams();
            params.set('limit', tracePaging.limit);
            params.set('offset', tracePaging.offset);
            const res = await fetch(`/v1/traces?${params.toString()}`);
            const data = await res.json();
            const items = Array.isArray(data) ? data : (data.items || []);
            setTraces(items.map(t => ({ ...t, showDetail: false })));
            if (!Array.isArray(data)) {
                setTracePaging(p => ({ ...p, limit: data.limit || p.limit, offset: data.offset || p.offset, total: data.total || 0 }));
            } else {
                setTracePaging(p => ({ ...p, offset: 0, total: items.length }));
            }
        } catch (e) {
            console.error('Error fetching traces:', e);
            setTraces([]);
        }
    };

    const fetchCaseDetail = async (c) => {
        try {
            const res = await fetch(`/v1/bug-cases/${c.case_id}`);
            const data = await res.json();
            setSelectedCase(data);
        } catch (e) {
            console.error('Error fetching case detail:', e);
            setSelectedCase(c); // Fallback to basic info
        }
    };

    useEffect(() => {
        if (view === 'library') fetchCases();
    }, [view, casePaging.offset, searchQuery]);

    useEffect(() => {
        if (view === 'history') fetchTraces();
    }, [view, tracePaging.offset]);

    useEffect(() => {
        if (view === 'library') setCasePaging(p => ({ ...p, offset: 0 }));
    }, [searchQuery]);

    const formatDate = (ts) => {
        if (!ts) return 'N/A';
        const d = ts.toString().length === 10 ? new Date(ts * 1000) : new Date(ts);
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    const toggleTraceDetail = async (id) => {
        const current = traces.find(t => t.trace_id === id);
        const opening = !(current && current.showDetail);
        if (!opening) {
            setTraces(prev => prev.map(t => t.trace_id === id ? { ...t, showDetail: false } : t));
            return;
        }
        setTraces(prev => prev.map(t => t.trace_id === id ? { ...t, showDetail: true } : t));
        if (current && current.detail) return;
        try {
            const res = await fetch(`/v1/traces/${id}`);
            const data = await res.json();
            setTraces(prev => prev.map(t => t.trace_id === id ? { ...t, detail: data, showDetail: true } : t));
        } catch (e) {
            console.error('Error fetching trace detail:', e);
        }
    };

    const debugTrace = (t) => {
        const text = (t.detail && t.detail.trace && t.detail.trace.error_excerpt) || t.error_excerpt || t.query || '';
        setDebugInput(text);
        setView('debug');
        // Optionally trigger retrieval immediately
    };

    const handleTestRetrieval = async () => {
        if (!debugInput.trim()) return;
        setLoading(true);
        setDebugResult(null);

        try {
            const res = await fetch('/v1/debug/retrieval', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ error_content: debugInput })
            });
            const data = await res.json();
            setDebugResult(data);
        } catch (e) {
            console.error('Error testing retrieval:', e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="app-container">
            <nav className="navbar">
                <div className="logo">
                    <span className="logo-icon">AI</span>
                    <span className="logo-text">AI-Ops Bug Fix Library</span>
                </div>
                <div className="nav-links">
                    <button className={view === 'library' ? 'active' : ''} onClick={() => setView('library')}>Library</button>
                    <button className={view === 'history' ? 'active' : ''} onClick={() => setView('history')}>History</button>
                    <button className={view === 'debug' ? 'active' : ''} onClick={() => setView('debug')}>Debug Tool</button>
                </div>
            </nav>

            <main className="container">
                {view === 'library' && (
                    <section className="view-section">
                        <header className="section-header">
                            <h1>Bug Fix cases</h1>
                            <div className="search-bar">
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Search cases by signature or exception..."
                                />
                            </div>
                        </header>

                        <div className="case-grid">
                            {cases.length === 0 && <div className="empty-state">No cases found.</div>}
                            {cases.map(c => (
                                <div key={c.case_id} className="case-card" onClick={() => fetchCaseDetail(c)}>
                                    <div className="card-glow"></div>
                                    <div className="card-content">
                                        <div className={`case-badge ${(c.exception_type || '').toLowerCase()}`}>{c.exception_type || 'Unknown'}</div>
                                        <h3 className="case-title">{c.message_key || 'No message'}</h3>
                                        <div className="case-info-sm">
                                            <span><strong>Repo:</strong> {(c.repo_url || '').split('/').pop()}</span>
                                            <span><strong>Sig:</strong> {(c.signature || '').substring(0, 8)}...</span>
                                        </div>
                                        <div className="case-meta">
                                            <span className="score">Quality Score: <strong>{Math.round((c.quality_score || 0) * 100)}%</strong></span>
                                            <span className="date">{formatDate(c.updated_at)}</span>
                                        </div>
                                        <div className="progress-bar">
                                            <div className="progress-fill" style={{ width: `${(c.quality_score || 0) * 100}%` }}></div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="action-btns" style={{ marginTop: '1.25rem', justifyContent: 'flex-end' }}>
                            <button
                                className="btn-outline"
                                onClick={() => setCasePaging(p => ({ ...p, offset: Math.max(0, p.offset - p.limit) }))}
                                disabled={casePaging.offset <= 0}
                            >
                                Prev
                            </button>
                            <button
                                className="btn-outline"
                                onClick={() => setCasePaging(p => ({ ...p, offset: p.offset + p.limit }))}
                                disabled={casePaging.total > 0 ? (casePaging.offset + casePaging.limit) >= casePaging.total : cases.length < casePaging.limit}
                            >
                                Next
                            </button>
                        </div>
                    </section>
                )}

                {view === 'history' && (
                    <section className="view-section">
                        <header className="section-header">
                            <h1>Call History</h1>
                            <p className="subtitle">History of all auto-repair execution tasks.</p>
                        </header>

                        <div className="history-table-container">
                            <table className="history-table">
                                <thead>
                                    <tr>
                                        <th>Trace ID</th>
                                        <th>Repo</th>
                                        <th>Status</th>
                                        <th>Created At</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                {traces.length === 0 && <tbody><tr><td colSpan="5" className="empty-state">No history records found.</td></tr></tbody>}
                                {traces.map(t => (
                                    <tbody key={t.trace_id}>
                                        <tr>
                                            <td className="mono">{(t.trace_id || '').substring(0, 8)}...</td>
                                            <td>{(t.repo_url || '').split('/').pop()}</td>
                                            <td>
                                                <span className={`status-badge ${(t.status || '').toLowerCase()}`}>{t.status}</span>
                                            </td>
                                            <td>{formatDate(t.created_at)}</td>
                                            <td>
                                                <div className="action-btns">
                                                    <button className="btn-small btn-outline" onClick={() => toggleTraceDetail(t.trace_id)}>
                                                        {t.showDetail ? 'Hide' : 'Info'}
                                                    </button>
                                                    <button className="btn-small btn-primary-lite" onClick={() => debugTrace(t)}>
                                                        Debug
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                        {t.showDetail && (
                                            <tr className="detail-row">
                                                <td colSpan="5">
                                                    <div className="trace-info-expanded">
                                                        <div className="info-block">
                                                            <strong>Original Error Excerpt:</strong>
                                                            <pre>{(t.detail && t.detail.trace && t.detail.trace.error_excerpt) || t.error_excerpt || t.query || 'No data available'}</pre>
                                                        </div>
                                                        <div className="info-block">
                                                            <strong>Status Message:</strong>
                                                            <span>{(t.detail && t.detail.trace && t.detail.trace.failure_message) || t.failure_message || 'OK'}</span>
                                                        </div>
                                                        {t.detail && t.detail.top_match && (
                                                            <div className="info-block">
                                                                <strong>Top Match</strong>
                                                                <div className="match-item">
                                                                    <div className="match-info">
                                                                        <div className="match-title">{t.detail.top_match.exception_type}</div>
                                                                        <div className="match-score">Score: {Math.round((t.detail.top_match.quality_score || 0) * 100)}%</div>
                                                                        <div className="match-msg">{t.detail.top_match.message_key}</div>
                                                                    </div>
                                                                    <button className="btn-small" onClick={() => { setSelectedCase(t.detail.top_match); fetchCaseDetail(t.detail.top_match); }}>View Case</button>
                                                                </div>
                                                            </div>
                                                        )}
                                                        {t.detail && Array.isArray(t.detail.steps) && t.detail.steps.length > 0 && (
                                                            <div className="info-block">
                                                                <strong>Execution Steps</strong>
                                                                <div className="frames-list">
                                                                    {t.detail.steps.map((s, i) => (
                                                                        <div key={i} className="frame-item">
                                                                            [{s.status}] {s.step_name} — {formatDate(s.started_at)}{s.finished_at ? ` → ${formatDate(s.finished_at)}` : ''}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                ))}
                            </table>
                        </div>
                        <div className="action-btns" style={{ marginTop: '1.25rem', justifyContent: 'flex-end' }}>
                            <button
                                className="btn-outline"
                                onClick={() => setTracePaging(p => ({ ...p, offset: Math.max(0, p.offset - p.limit) }))}
                                disabled={tracePaging.offset <= 0}
                            >
                                Prev
                            </button>
                            <button
                                className="btn-outline"
                                onClick={() => setTracePaging(p => ({ ...p, offset: p.offset + p.limit }))}
                                disabled={tracePaging.total > 0 ? (tracePaging.offset + tracePaging.limit) >= tracePaging.total : traces.length < tracePaging.limit}
                            >
                                Next
                            </button>
                        </div>
                    </section>
                )}

                {view === 'debug' && (
                    <section className="view-section">
                        <header className="section-header">
                            <h1>Retrieval Debugger</h1>
                            <p className="subtitle">Paste a traceback to test the system's ability to find matching bug cases.</p>
                        </header>

                        <div className="debug-layout">
                            <div className="debug-input">
                                <textarea
                                    value={debugInput}
                                    onChange={(e) => setDebugInput(e.target.value)}
                                    placeholder="Paste log trace here..."
                                />
                                <button className="btn-primary" onClick={handleTestRetrieval} disabled={loading}>
                                    {!loading ? 'Test Retrieval' : 'Processing...'}
                                </button>
                            </div>

                            {debugResult && (
                                <div className="debug-output">
                                    <div className="output-card features">
                                        <h3>Extracted Features</h3>
                                        <div className="feature-tags">
                                            <div className="tag"><strong>Type:</strong> {debugResult.features.exception_type}</div>
                                            {debugResult.features.signature && (
                                                <div className="tag signature"><strong>Sig:</strong> {debugResult.features.signature.substring(0, 12)}...</div>
                                            )}
                                        </div>
                                        <div className="code-snippet">
                                            <pre>{debugResult.features.normalized_query}</pre>
                                        </div>
                                    </div>

                                    <div className="output-card results">
                                        <h3>Debugger Match Results</h3>
                                        {debugResult.matches.length === 0 ? (
                                            <div className="empty-state">No similar cases found in library.</div>
                                        ) : (
                                            debugResult.matches.map((match, index) => (
                                                <div key={index} className="match-item">
                                                    <div className="match-rank">#{index + 1}</div>
                                                    <div className="match-info">
                                                        <div className="match-title">{match.exception_type}</div>
                                                        <div className="match-score">Score: {Math.round((match.quality_score || 0) * 100)}%</div>
                                                        <div className="match-msg">{match.message_key}</div>
                                                    </div>
                                                    <button className="btn-small" onClick={() => { setSelectedCase(match); fetchCaseDetail(match); }}>View Case</button>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </section>
                )}
            </main>

            {selectedCase && (
                <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setSelectedCase(null)}>
                    <div className="modal-card">
                        <button className="modal-close" onClick={() => setSelectedCase(null)}>&times;</button>
                        <header className="modal-header">
                            <h2>{selectedCase.exception_type || 'Case Details'}</h2>
                            <p>{selectedCase.message_key}</p>
                        </header>
                        <div className="modal-tabs">
                            <button className="tab-btn active">Overview</button>
                            <button className="tab-btn">Revisions ({(selectedCase.revisions || []).length})</button>
                        </div>
                        <div className="modal-body">
                            <div className="info-group">
                                <label>Signature Hash (SHA-256)</label>
                                <code>{selectedCase.signature}</code>
                            </div>
                            <div className="info-grid">
                                <div className="info-group">
                                    <label>Repository</label>
                                    <a href={selectedCase.repo_url} target="_blank">{selectedCase.repo_url}</a>
                                </div>
                                <div className="info-group">
                                    <label>Code Host</label>
                                    <span>{selectedCase.code_host}</span>
                                </div>
                            </div>
                            <div className="info-group">
                                <label>Top Stack Frames</label>
                                <div className="frames-list">
                                    {(selectedCase.top_frames || '').split('|').map((frame, i) => (
                                        <div key={i} className="frame-item">{frame.trim()}</div>
                                    ))}
                                    {!(selectedCase.top_frames) && <span>No frames recorded.</span>}
                                </div>
                            </div>

                            {(selectedCase.revisions || []).length > 0 && (
                                <div className="revisions-list">
                                    <label>Recent Revisions</label>
                                    {selectedCase.revisions.map((rev, i) => (
                                        <div key={i} className="rev-item">
                                            <span className="rev-type">{rev.trigger_type}</span>
                                            <a href={rev.pr_url || '#'} target="_blank" className="rev-link">
                                                {rev.commit_sha ? rev.commit_sha.substring(0, 7) : 'View Pull Request'}
                                            </a>
                                            <span className="rev-date">{formatDate(rev.created_at)}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
