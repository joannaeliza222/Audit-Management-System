// Enhanced AMS JavaScript functionality
class EnhancedAMS {
    constructor() {
        this.apiBase = '/api/enhanced';
        this.charts = {};
        this.init();
    }

    init() {
        this.initializeCharts();
        this.loadDashboardData();
        this.setupEventListeners();
        this.startRealTimeUpdates();
    }

    // Initialize dashboard charts
    initializeCharts() {
        // Check if Chart.js is loaded
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded. Charts will not be initialized.');
            return;
        }
        
        // Chart initialization removed - Query Trends and Commitment Status charts disabled
    }

    // Load dashboard data
    async loadDashboardData() {
        try {
            const response = await fetch(`${this.apiBase}/analytics/performance`);
            const data = await response.json();
            
            if (data.success) {
                this.updateKPICards(data.analytics);
                this.updateCharts(data.analytics);
                this.loadRecentActivity();
            }
        } catch (error) {
            console.error('Error loading dashboard data:', error);
            this.showError('Failed to load dashboard data');
        }
    }

    // Update KPI cards
    updateKPICards(data) {
        // Update counts
        this.updateElement('pending-count', data.query_volume?.by_status?.received || 0);
        this.updateElement('answered-count', data.query_volume?.by_status?.responded || 0);
        this.updateElement('total-states-count', data.total_states || 0);
        this.updateElement('ai-accuracy', `${(data.ai_performance?.similarity_matches_found || 0).toFixed(1)}%`);
    }

    // Update charts function removed - charts disabled

    // Generate date labels for charts
    generateDateLabels(days) {
        const labels = [];
        const today = new Date();
        
        for (let i = days - 1; i >= 0; i--) {
            const date = new Date(today);
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        }
        
        return labels;
    }

    // Generate mock data for demonstration
    generateMockData(count, min, max) {
        const data = [];
        for (let i = 0; i < count; i++) {
            data.push(Math.floor(Math.random() * (max - min + 1)) + min);
        }
        return data;
    }

    // Load recent activity
    async loadRecentActivity() {
        try {
            // Mock recent activity data
            const activities = [
                {
                    timestamp: new Date().toISOString(),
                    query_id: 'AUD-2024-001',
                    state: 'California',
                    action: 'Created with AI analysis',
                    status: 'received',
                    ai_confidence: 0.87
                },
                {
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    query_id: 'AUD-2024-002',
                    state: 'Texas',
                    action: 'Response suggested',
                    status: 'in_progress',
                    ai_confidence: 0.92
                },
                {
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    query_id: 'AUD-2024-003',
                    state: 'New York',
                    action: 'Commitment detected',
                    status: 'awaiting_response',
                    ai_confidence: 0.78
                }
            ];

            this.updateRecentActivityTable(activities);
        } catch (error) {
            console.error('Error loading recent activity:', error);
        }
    }

    // Update recent activity table
    updateRecentActivityTable(activities) {
        const tbody = document.getElementById('recentActivityBody');
        if (!tbody) return;

        tbody.innerHTML = activities.map(activity => `
            <tr>
                <td>${new Date(activity.timestamp).toLocaleString()}</td>
                <td><span class="badge bg-primary">${activity.query_id}</span></td>
                <td>${activity.state}</td>
                <td>${activity.action}</td>
                <td><span class="badge bg-${this.getStatusColor(activity.status)}">${activity.status}</span></td>
                <td>
                    <div class="d-flex align-items-center gap-1">
                        <div class="progress" style="width: 60px; height: 8px;">
                            <div class="progress-bar bg-${this.getConfidenceColor(activity.ai_confidence)}" 
                                 style="width: ${activity.ai_confidence * 100}%"></div>
                        </div>
                        <small>${(activity.ai_confidence * 100).toFixed(0)}%</small>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    // Get status color for badges
    getStatusColor(status) {
        const colors = {
            'received': 'secondary',
            'in_progress': 'primary',
            'awaiting_response': 'warning',
            'responded': 'success',
            'closed': 'dark'
        };
        return colors[status] || 'secondary';
    }

    // Get confidence color
    getConfidenceColor(confidence) {
        if (confidence >= 0.8) return 'success';
        if (confidence >= 0.6) return 'warning';
        return 'danger';
    }

    // Setup event listeners
    setupEventListeners() {
        // Auto-refresh disabled - no longer refreshing every 5 minutes
        // setInterval(() => {
        //     this.loadDashboardData();
        // }, 300000);
    }

    // Start real-time updates
    startRealTimeUpdates() {
        // WebSocket connection for real-time updates (if implemented)
        // Real-time updates disabled - no longer refreshing every minute
        // setInterval(() => {
        //     this.refreshActivity();
        // }, 60000); // Every minute
    }

    // Helper method to update elements
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    // Show error message
    showError(message) {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = 'toast align-items-center text-white bg-danger border-0';
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        document.body.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    // Show success message
    showSuccess(message) {
        const toast = document.createElement('div');
        toast.className = 'toast align-items-center text-white bg-success border-0';
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        document.body.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
}

// Query Management Functions
class QueryManager {
    constructor() {
        this.apiBase = '/api/enhanced';
    }

    // Show create query modal
    showCreateQueryModal() {
        const modal = new bootstrap.Modal(document.getElementById('createQueryModal'));
        modal.show();
    }

    // Create new query
    async createQuery() {
        const form = document.getElementById('createQueryForm');
        const formData = new FormData(form);
        
        const queryData = {
            subject: document.getElementById('querySubject').value,
            query_description: document.getElementById('queryDescription').value,
            state_name: document.getElementById('stateName').value,
            query_date: document.getElementById('queryDate').value
        };

        try {
            const response = await fetch(`${this.apiBase}/queries`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(queryData)
            });

            const result = await response.json();
            
            if (result.success) {
                enhancedAMS.showSuccess(`Query ${result.data.query.query_id} created successfully!`);
                bootstrap.Modal.getInstance(document.getElementById('createQueryModal')).hide();
                form.reset();
                enhancedAMS.loadDashboardData();
            } else {
                enhancedAMS.showError('Failed to create query: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating query:', error);
            enhancedAMS.showError('Failed to create query. Please try again.');
        }
    }
}

// Commitment Monitoring Functions
class CommitmentMonitor {
    constructor() {
        this.apiBase = '/api/enhanced';
    }

    // Show commitment monitoring
    async showCommitmentMonitoring() {
        try {
            const response = await fetch(`${this.apiBase}/commitments/monitoring`);
            const result = await response.json();
            
            if (result.success) {
                this.displayCommitmentMonitoring(result.monitoring_data);
            } else {
                enhancedAMS.showError('Failed to load commitment data');
            }
        } catch (error) {
            console.error('Error loading commitment monitoring:', error);
            enhancedAMS.showError('Failed to load commitment data');
        }
    }

    // Display commitment monitoring data
    displayCommitmentMonitoring(data) {
        // Create modal for commitment monitoring
        const modalHtml = `
            <div class="modal fade" id="commitmentMonitoringModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Commitment Monitoring Dashboard</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row g-3">
                                <div class="col-md-4">
                                    <div class="card border-danger">
                                        <div class="card-header bg-danger text-white">
                                            <h6 class="m-0">Overdue Commitments</h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="h3 text-danger">${data.overdue_commitments.length}</div>
                                            ${data.overdue_commitments.slice(0, 3).map(commitment => `
                                                <div class="small text-muted">
                                                    <strong>${commitment.query_id}:</strong> ${commitment.text?.substring(0, 50)}...
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="card border-warning">
                                        <div class="card-header bg-warning text-dark">
                                            <h6 class="m-0">Upcoming Deadlines</h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="h3 text-warning">${data.upcoming_deadlines.length}</div>
                                            ${data.upcoming_deadlines.slice(0, 3).map(commitment => `
                                                <div class="small text-muted">
                                                    <strong>${commitment.query_id}:</strong> ${commitment.days_until_target} days
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="card border-success">
                                        <div class="card-header bg-success text-white">
                                            <h6 class="m-0">Summary</h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="small">
                                                <strong>Total:</strong> ${data.summary.total_commitments}<br>
                                                <strong>Completion Rate:</strong> ${(data.summary.completion_rate * 100).toFixed(1)}%<br>
                                                <strong>Overdue:</strong> ${data.summary.overdue_count}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            ${data.recommendations.length > 0 ? `
                                <div class="mt-3">
                                    <h6>Recommendations</h6>
                                    ${data.recommendations.map(rec => `
                                        <div class="alert alert-${rec.priority === 'high' ? 'danger' : 'warning'}">
                                            <strong>${rec.type}:</strong> ${rec.message}
                                        </div>
                                    `).join('')}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('commitmentMonitoringModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add new modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('commitmentMonitoringModal'));
        modal.show();
    }
}

// Analytics Functions
class AnalyticsManager {
    constructor() {
        this.apiBase = '/api/enhanced';
    }

    // Show data dump analytics
    showDataDumpAnalytics() {
        // Redirect to data dump analytics page
        window.location.href = '/data-dump-analytics';
    }

    // Show performance analytics
    async showPerformanceAnalytics() {
        try {
            const response = await fetch(`${this.apiBase}/analytics/performance?days=30`);
            const result = await response.json();
            
            if (result.success) {
                this.displayPerformanceAnalytics(result.analytics);
            } else {
                enhancedAMS.showError('Failed to load performance data');
            }
        } catch (error) {
            console.error('Error loading performance analytics:', error);
            enhancedAMS.showError('Failed to load performance data');
        }
    }

    // Display performance analytics
    displayPerformanceAnalytics(data) {
        const modalHtml = `
            <div class="modal fade" id="performanceAnalyticsModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Performance Analytics (Last 30 Days)</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row g-3">
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="m-0">Query Volume</h6>
                                        </div>
                                        <div class="card-body">
                                            <p><strong>Total Queries:</strong> ${data.query_volume?.total_queries || 0}</p>
                                            <p><strong>Daily Average:</strong> ${data.query_volume?.daily_average?.toFixed(1) || 0}</p>
                                            <p><strong>Response Rate:</strong> ${((data.response_times?.response_rate || 0) * 100).toFixed(1)}%</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="m-0">Response Times</h6>
                                        </div>
                                        <div class="card-body">
                                            <p><strong>Average:</strong> ${data.response_times?.average_days?.toFixed(1) || 0} days</p>
                                            <p><strong>Median:</strong> ${data.response_times?.median_days || 0} days</p>
                                            <p><strong>Total Responded:</strong> ${data.response_times?.total_responded || 0}</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="m-0">Commitments</h6>
                                        </div>
                                        <div class="card-body">
                                            <p><strong>Total:</strong> ${data.commitments?.total_commitments || 0}</p>
                                            <p><strong>Completion Rate:</strong> ${((data.commitments?.completion_rate || 0) * 100).toFixed(1)}%</p>
                                            <p><strong>Overdue:</strong> ${data.commitments?.by_status?.overdue || 0}</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="m-0">AI Performance</h6>
                                        </div>
                                        <div class="card-body">
                                            <p><strong>Cache Hit Rate:</strong> ${((data.ai_performance?.cache_hit_rate || 0) * 100).toFixed(1)}%</p>
                                            <p><strong>Avg Analysis Time:</strong> ${data.ai_performance?.avg_analysis_time_ms || 0}ms</p>
                                            <p><strong>Similarity Accuracy:</strong> ${((data.ai_performance?.similarity_search_accuracy || 0) * 100).toFixed(1)}%</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('performanceAnalyticsModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add new modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('performanceAnalyticsModal'));
        modal.show();
    }

    // Show AI analytics
    async showAIAnalytics() {
        try {
            const response = await fetch(`${this.apiBase}/ai/model-performance`);
            const result = await response.json();
            
            if (result.success) {
                this.displayAIAnalytics(result.ai_performance);
            } else {
                enhancedAMS.showError('Failed to load AI performance data');
            }
        } catch (error) {
            console.error('Error loading AI analytics:', error);
            enhancedAMS.showError('Failed to load AI performance data');
        }
    }

    // Display AI analytics
    displayAIAnalytics(data) {
        const modalHtml = `
            <div class="modal fade" id="aiAnalyticsModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">AI Model Performance</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row g-3">
                                <div class="col-12">
                                    <h6>Active Models</h6>
                                    ${Object.entries(data.models).map(([name, model]) => `
                                        <div class="card mb-2">
                                            <div class="card-body">
                                                <div class="row">
                                                    <div class="col-md-6">
                                                        <strong>${model.model_name}</strong><br>
                                                        <small class="text-muted">Status: ${model.status}</small>
                                                    </div>
                                                    <div class="col-md-6">
                                                        <small>Memory: ${model.memory_usage_mb}MB</small><br>
                                                        <small>Daily Requests: ${model.daily_requests}</small>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                                <div class="col-12">
                                    <h6>Performance Metrics</h6>
                                    <div class="row">
                                        <div class="col-md-4">
                                            <div class="text-center">
                                                <div class="h4">${(data.performance.similarity_search_accuracy * 100).toFixed(1)}%</div>
                                                <small class="text-muted">Similarity Accuracy</small>
                                            </div>
                                        </div>
                                        <div class="col-md-4">
                                            <div class="text-center">
                                                <div class="h4">${data.performance.avg_analysis_time_ms}ms</div>
                                                <small class="text-muted">Avg Analysis Time</small>
                                            </div>
                                        </div>
                                        <div class="col-md-4">
                                            <div class="text-center">
                                                <div class="h4">${(data.performance.cache_hit_rate * 100).toFixed(1)}%</div>
                                                <small class="text-muted">Cache Hit Rate</small>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('aiAnalyticsModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add new modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('aiAnalyticsModal'));
        modal.show();
    }
}

// Global functions for onclick handlers
let enhancedAMS;
let queryManager;
let commitmentMonitor;
let analyticsManager;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    enhancedAMS = new EnhancedAMS();
    queryManager = new QueryManager();
    commitmentMonitor = new CommitmentMonitor();
    analyticsManager = new AnalyticsManager();
    
    // Set current date as default for query date field
    const queryDateField = document.getElementById('queryDate');
    if (queryDateField) {
        const today = new Date().toISOString().split('T')[0];
        queryDateField.value = today;
    }
});

// Global functions for HTML onclick handlers
function showCreateQueryModal() {
    if (typeof queryManager !== 'undefined' && queryManager) {
        queryManager.showCreateQueryModal();
    } else {
        console.warn('QueryManager is not initialized');
        // Fallback: redirect to create query page
        window.location.href = '/create-query';
    }
}

function createQuery() {
    if (typeof queryManager !== 'undefined' && queryManager) {
        queryManager.createQuery();
    } else {
        console.warn('QueryManager is not initialized');
        // Fallback: redirect to create query page
        window.location.href = '/create-query';
    }
}

function showCommitmentMonitoring() {
    if (typeof commitmentMonitor !== 'undefined' && commitmentMonitor) {
        commitmentMonitor.showCommitmentMonitoring();
    } else {
        console.warn('CommitmentMonitor is not initialized');
        // Fallback: redirect to commitment dashboard
        window.location.href = '/commitment-dashboard';
    }
}

function showPerformanceAnalytics() {
    if (typeof analyticsManager !== 'undefined' && analyticsManager) {
        analyticsManager.showPerformanceAnalytics();
    } else {
        console.warn('AnalyticsManager is not initialized');
        // Fallback: redirect to analytics dashboard
        window.location.href = '/analytics';
    }
}

function showDataDumpAnalytics() {
    if (typeof analyticsManager !== 'undefined' && analyticsManager) {
        analyticsManager.showDataDumpAnalytics();
    } else {
        console.warn('AnalyticsManager is not initialized');
        // Fallback: redirect to data dump analytics page
        window.location.href = '/data-dump-analytics';
    }
}

function showAIAnalytics() {
    if (typeof analyticsManager !== 'undefined' && analyticsManager) {
        analyticsManager.showAIAnalytics();
    } else {
        console.warn('AnalyticsManager is not initialized');
        // Fallback: redirect to analytics dashboard
        window.location.href = '/analytics';
    }
}

// refreshActivity function removed - Recent Activity section removed

// Ask Your Database Functions
function toggleSQLQuery() {
    const section = document.getElementById('sqlQuerySection');
    const icon = document.getElementById('sqlToggleIcon');
    
    if (section.style.display === 'none') {
        section.style.display = 'block';
        icon.classList.remove('bi-chevron-down');
        icon.classList.add('bi-chevron-up');
    } else {
        section.style.display = 'none';
        icon.classList.remove('bi-chevron-up');
        icon.classList.add('bi-chevron-down');
    }
}

function toggleSQLCode() {
    const container = document.getElementById('sqlCodeContainer');
    container.style.display = container.style.display === 'none' ? 'block' : 'none';
}

async function askDatabase() {
    const question = document.getElementById('naturalLanguageQuestion').value.trim();
    
    if (!question) {
        enhancedAMS.showError('Please enter a question');
        return;
    }
    
    // Show loading state
    document.getElementById('sqlLoading').style.display = 'block';
    document.getElementById('sqlError').style.display = 'none';
    document.getElementById('sqlResults').style.display = 'none';
    
    try {
        const response = await fetch('/api/ask-db', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question: question }),
            credentials: 'same-origin'
        });
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            throw new Error('Server returned non-JSON response. You may need to log in again.');
        }

        const data = await response.json();

        // Hide loading state
        document.getElementById('sqlLoading').style.display = 'none';
        
        if (data.success) {
            // Show SQL code
            document.getElementById('sqlCode').textContent = data.sql;
            
            // Build results table
            const thead = document.getElementById('sqlResultsTableHead');
            const tbody = document.getElementById('sqlResultsTableBody');
            
            thead.innerHTML = '<tr>' + data.columns.map(col => `<th>${col}</th>`).join('') + '</tr>';
            
            tbody.innerHTML = data.rows.map(row => 
                '<tr>' + data.columns.map(col => `<td>${row[col] !== null ? row[col] : ''}</td>`).join('') + '</tr>'
            ).join('');
            
            // Show results count
            document.getElementById('sqlResultsCount').textContent = `Showing ${data.rows.length} row(s)`;
            
            // Show results section
            document.getElementById('sqlResults').style.display = 'block';
        } else {
            // Show error
            document.getElementById('sqlErrorMessage').textContent = data.error;
            document.getElementById('sqlError').style.display = 'block';
            
            // Show SQL if available
            if (data.sql && data.sql !== 'N/A') {
                document.getElementById('sqlCode').textContent = data.sql;
                document.getElementById('sqlCodeContainer').style.display = 'block';
            }
        }
    } catch (error) {
        document.getElementById('sqlLoading').style.display = 'none';
        document.getElementById('sqlErrorMessage').textContent = 'Failed to process question: ' + error.message;
        document.getElementById('sqlError').style.display = 'block';
    }
}

// updateQueryChart function removed - charts disabled

// Additional functions for future implementation
function showDocumentUpload() {
    const modal = new bootstrap.Modal(document.getElementById('documentUploadModal'));
    modal.show();
}

function showFAQUploadModal() {
    const modal = new bootstrap.Modal(document.getElementById('faqUploadModal'));
    modal.show();
}

function uploadDocument() {
    const fileInput = document.getElementById('documentFile');
    const description = document.getElementById('documentDescription').value;
    
    if (!fileInput.files || fileInput.files.length === 0) {
        enhancedAMS.showError('Please select a file to upload');
        return;
    }
    
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);
    if (description) {
        formData.append('description', description);
    }
    
    // Add CSRF token if available
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (csrfToken) {
        formData.append('csrf_token', csrfToken);
    }
    
    fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': csrfToken || ''
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            enhancedAMS.showError(data.error);
        } else {
            enhancedAMS.showSuccess('Document uploaded successfully');
            const modal = bootstrap.Modal.getInstance(document.getElementById('documentUploadModal'));
            modal.hide();
            fileInput.value = '';
            document.getElementById('documentDescription').value = '';
        }
    })
    .catch(error => {
        enhancedAMS.showError('Failed to upload document: ' + error.message);
    });
}

function showKnowledgeBase() {
    enhancedAMS.showError('Knowledge base feature coming soon!');
}

function showDocumentQA() {
    enhancedAMS.showError('Document Q&A feature coming soon!');
}

function showQueryInsights() {
    enhancedAMS.showError('Query insights feature coming soon!');
}

// Functionality Card Functions
function showUploadModal() {
    // Redirect to document upload page or show modal
    window.location.href = '/upload';
}

function showTemplateInfo() {
    const info = `
        <div class="template-info">
            <h6>FAQ Template Information</h6>
            <p><strong>File Format:</strong> Excel (.xlsx)</p>
            <p><strong>Required Columns:</strong></p>
            <ul>
                <li>Subject - Brief description of the query</li>
                <li>Query Details: Detailed description of the query</li>
                <li>Memo ID - memo identifier</li>
                <li>Answer - The corresponding answer</li>
                <li>State - State name</li>
                <li>Priority - Priority level (High/Medium/Low)</li>
            </ul>
            <p><strong>Maximum Rows:</strong> 1000</p>
            <p><strong>File Size Limit:</strong> 10MB</p>
            <p class="text-muted">Download the template and fill it with your FAQ data before uploading.</p>
        </div>
    `;
    
    // Create a modal to show template info
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Template Information</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    ${info}
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <a href="/static/faq_template.xlsx" class="btn btn-success" download>
                        <i class="bi bi-download"></i> Download Template
                    </a>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // Clean up after modal is hidden
    modal.addEventListener('hidden.bs.modal', () => {
        document.body.removeChild(modal);
    });
}

function showRequestDumpModal() {
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Request Data Dump</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="requestDumpForm">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="dumpState" class="form-label">State *</label>
                                    <select class="form-select" id="dumpState" name="state" required>
                                        <option value="">Select State</option>
                                        <option value="Andhra Pradesh">Andhra Pradesh</option>
                                        <option value="Arunachal Pradesh">Arunachal Pradesh</option>
                                        <option value="Assam">Assam</option>
                                        <option value="Bihar">Bihar</option>
                                        <option value="Goa">Goa</option>
                                        <option value="Gujarat">Gujarat</option>
                                        <option value="Haryana">Haryana</option>
                                        <option value="Himachal Pradesh">Himachal Pradesh</option>
                                        <option value="Jharkhand">Jharkhand</option>
                                        <option value="Karnataka">Karnataka</option>
                                        <option value="Kerala">Kerala</option>
                                        <option value="Madhya Pradesh">Madhya Pradesh</option>
                                        <option value="Maharashtra">Maharashtra</option>
                                        <option value="Meghalaya">Meghalaya</option>
                                        <option value="Nagaland">Nagaland</option>
                                        <option value="Odisha">Odisha</option>
                                        <option value="Punjab">Punjab</option>
                                        <option value="Rajasthan">Rajasthan</option>
                                        <option value="Tamil Nadu">Tamil Nadu</option>
                                        <option value="Telangana">Telangana</option>
                                        <option value="Uttar Pradesh">Uttar Pradesh</option>
                                        <option value="West Bengal">West Bengal</option>
                                        <option value="Uttarakhand">Uttarakhand</option>
                                        <option value="Delhi">Delhi</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="dumpNodalDepartment" class="form-label">Nodal Department *</label>
                                    <input type="text" class="form-control" id="dumpNodalDepartment" name="nodal_department" required 
                                           placeholder="Enter nodal department name">
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="dumpCoordinator" class="form-label">Coordinator *</label>
                                    <input type="text" class="form-control" id="dumpCoordinator" name="coordinator" required 
                                           placeholder="Enter coordinator name">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="dumpDate" class="form-label">Request Date *</label>
                                    <input type="date" class="form-control" id="dumpDate" name="request_date" required>
                                </div>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label for="dumpRequest" class="form-label">Request Details *</label>
                            <textarea class="form-control" id="dumpRequest" name="request_details" rows="4" required 
                                      placeholder="Describe your data dump request in detail"></textarea>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-info" onclick="submitDataDumpRequest()">
                        <i class="bi bi-send"></i> Submit Request
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    
    // Set current date as default for request date
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('dumpDate').value = today;
    
    bsModal.show();
    
    // Clean up after modal is hidden
    modal.addEventListener('hidden.bs.modal', () => {
        document.body.removeChild(modal);
    });
}

function submitDataDumpRequest() {
    const form = document.getElementById('requestDumpForm');
    const formData = new FormData(form);
    
    fetch('/request_dump', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            enhancedAMS.showSuccess('Data dump request submitted successfully!');
            // Close the modal
            const modal = document.querySelector('.modal.show');
            if (modal) {
                bootstrap.Modal.getInstance(modal).hide();
            }
        } else {
            enhancedAMS.showError(data.error || 'Failed to submit request');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        enhancedAMS.showError('Error submitting request');
    });
}

// Chatbot Toggle Functions
function toggleChatbot() {
    const chatbotContainer = document.getElementById('chatbotContainer');
    const chatbotToggle = document.getElementById('chatbotToggle');
    
    if (chatbotContainer.style.display === 'none') {
        chatbotContainer.style.display = 'flex';
        chatbotToggle.innerHTML = '<i class="bi bi-chat-dots-fill"></i> AI Assistant';
        chatbotToggle.classList.remove('btn-success');
        chatbotToggle.classList.add('btn-outline-success');
        
        // Focus on input when opened
        setTimeout(() => {
            document.getElementById('chatbotInput').focus();
        }, 300);
    } else {
        chatbotContainer.style.display = 'none';
        chatbotToggle.innerHTML = '<i class="bi bi-chat-dots"></i> AI Assistant';
        chatbotToggle.classList.remove('btn-outline-success');
        chatbotToggle.classList.add('btn-success');
    }
}

function clearChatbot() {
    const messagesContainer = document.getElementById('chatbotMessages');
    messagesContainer.innerHTML = `
        <div class="message ai">
            <div class="message-avatar">
                <i class="bi bi-robot"></i>
            </div>
            <div class="message-content">
                Hello! I'm your AI assistant. I can help you with questions about the Audit Management System. What would you like to know?
            </div>
        </div>
    `;
}

function sendChatbotMessage() {
    const input = document.getElementById('chatbotInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Add user message
    addChatbotMessage(message, 'user');
    
    // Clear input
    input.value = '';
    input.style.height = 'auto';
    
    // Show typing indicator
    showChatbotTyping();
    
    // Send to chatbot API
    fetch('/api/enhanced-chatbot/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message })
    })
    .then(response => response.json())
    .then(data => {
        removeChatbotTyping();
        if (data.response) {
            addChatbotMessage(data.response, 'ai');
        } else {
            addChatbotMessage('I apologize, but I encountered an error processing your request.', 'ai');
        }
    })
    .catch(error => {
        removeChatbotTyping();
        console.error('Chatbot error:', error);
        addChatbotMessage('I apologize, but I encountered an error processing your request.', 'ai');
    });
}

function sendChatbotSuggestion(suggestion) {
    document.getElementById('chatbotInput').value = suggestion;
    sendChatbotMessage();
}

function handleChatbotKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendChatbotMessage();
    }
    
    // Auto-resize textarea
    event.target.style.height = 'auto';
    event.target.style.height = Math.min(event.target.scrollHeight, 80) + 'px';
}

function addChatbotMessage(message, sender) {
    const messagesContainer = document.getElementById('chatbotMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatar = sender === 'user' ? 
        '<i class="bi bi-person"></i>' : 
        '<i class="bi bi-robot"></i>';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            ${avatar}
        </div>
        <div class="message-content">
            ${message}
        </div>
    `;
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showChatbotTyping() {
    const messagesContainer = document.getElementById('chatbotMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message ai typing-indicator';
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="bi bi-robot"></i>
        </div>
        <div class="message-content">
            <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function removeChatbotTyping() {
    const typingIndicator = document.querySelector('.typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Add typing dots CSS
const typingStyles = document.createElement('style');
typingStyles.textContent = `
    .typing-dots {
        display: flex;
        gap: 4px;
        padding: 8px 0;
    }
    
    .typing-dots span {
        width: 6px;
        height: 6px;
        background: #666;
        border-radius: 50%;
        animation: typing 1.4s infinite;
    }
    
    .typing-dots span:nth-child(1) { animation-delay: 0s; }
    .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
    .typing-dots span:nth-child(3) { animation-delay: 0.4s; }
    
    @keyframes typing {
        0%, 60%, 100% { transform: scale(0.8); opacity: 0.5; }
        30% { transform: scale(1); opacity: 1; }
    }
`;
document.head.appendChild(typingStyles);
