/**
 * Transcribe Tab functionality
 */

// State for transcribe tab
let transcribeFiles = [];
let transcribeEventSource = null;
let transcribeElapsedTimer = null;
let transcribeStartTime = null;

/**
 * Scan files for transcription
 */
async function scanTranscribeFiles() {
    const response = await fetch('/api/files');
    transcribeFiles = await response.json();
    renderTranscribeFileList();
}

/**
 * Render file list in transcribe tab
 */
function renderTranscribeFileList() {
    const container = document.getElementById('transcribeFileListContainer');
    const actions = document.getElementById('transcribeFileActions');

    if (transcribeFiles.length === 0) {
        container.innerHTML = '<div class="empty-state">没有找到音频文件</div>';
        actions.style.display = 'none';
        return;
    }

    container.innerHTML = `
        <div class="file-list">
            ${transcribeFiles.map((file, index) => `
                <div class="file-item">
                    <input type="checkbox" id="transcribe-file-${index}" ${file.status !== 'completed' ? 'checked' : ''}>
                    <span class="file-name">${file.name}</span>
                    <div class="file-tags">
                        ${file.has_lyric ? '<span class="tag tag-success">有歌词</span>' : '<span class="tag tag-warning">无歌词</span>'}
                        ${file.has_output ? '<span class="tag tag-success">有输出</span>' : '<span class="tag tag-warning">无输出</span>'}
                        ${file.has_lyric && file.has_output ? '<span class="tag-completed">✓</span>' : ''}
                    </div>
                </div>
            `).join('')}
        </div>
    `;

    actions.style.display = 'flex';
    updateTranscribeSelectionCount();

    // Add event listeners to checkboxes
    transcribeFiles.forEach((_, index) => {
        document.getElementById(`transcribe-file-${index}`).addEventListener('change', updateTranscribeSelectionCount);
    });
}

/**
 * Get selected files for transcription
 */
function getSelectedTranscribeFiles() {
    return transcribeFiles.filter((_, index) => {
        const checkbox = document.getElementById(`transcribe-file-${index}`);
        return checkbox && checkbox.checked;
    }).map(f => f.name);
}

/**
 * Update selection count display
 */
function updateTranscribeSelectionCount() {
    const count = getSelectedTranscribeFiles().length;
    document.getElementById('transcribeSelectionCount').textContent = `已选择 ${count} 个文件`;
}

/**
 * Select all files
 */
function selectAllTranscribe() {
    transcribeFiles.forEach((_, index) => {
        const checkbox = document.getElementById(`transcribe-file-${index}`);
        if (checkbox) checkbox.checked = true;
    });
    updateTranscribeSelectionCount();
}

/**
 * Deselect all files
 */
function selectNoneTranscribe() {
    transcribeFiles.forEach((_, index) => {
        const checkbox = document.getElementById(`transcribe-file-${index}`);
        if (checkbox) checkbox.checked = false;
    });
    updateTranscribeSelectionCount();
}

/**
 * Inverse selection
 */
function selectInverseTranscribe() {
    transcribeFiles.forEach((_, index) => {
        const checkbox = document.getElementById(`transcribe-file-${index}`);
        if (checkbox) checkbox.checked = !checkbox.checked;
    });
    updateTranscribeSelectionCount();
}

/**
 * Start transcription task
 */
async function startTranscribeTask() {
    const selectedFiles = getSelectedTranscribeFiles();
    if (selectedFiles.length === 0) {
        alert('请选择要处理的文件');
        return;
    }

    // Show progress section and connect SSE BEFORE starting task
    showTranscribeProgressSection();

    // Wait for SSE connection to be established
    await connectTranscribeSSE();

    const response = await fetch('/api/task/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: selectedFiles }),
    });

    if (!response.ok) {
        const error = await response.json();
        alert(error.detail || '启动任务失败');
        // Cleanup on failure
        hideTranscribeProgressSection();
        if (transcribeEventSource) {
            transcribeEventSource.close();
            transcribeEventSource = null;
        }
        return;
    }
}

/**
 * Cancel transcription task
 */
async function cancelTranscribeTask() {
    await fetch('/api/task/cancel', { method: 'POST' });
    if (transcribeEventSource) {
        transcribeEventSource.close();
        transcribeEventSource = null;
    }
}

/**
 * Check task status on page load
 */
async function checkTranscribeTaskStatus() {
    const response = await fetch('/api/task/status');
    const status = await response.json();

    if (status.running) {
        showTranscribeProgressSection(status.start_time);

        // Render recent output
        const log = document.getElementById('transcribeOutputLog');
        log.innerHTML = '';
        status.recent_output.forEach(event => {
            appendTranscribeLogEvent(event.type, event.data);
        });

        // Update progress
        if (status.progress) {
            updateTranscribeProgress(status.progress);
        }

        // Connect to SSE for live updates
        connectTranscribeSSE();
    }
}

/**
 * Show progress section
 */
function showTranscribeProgressSection(serverStartTime = null) {
    const progressSection = document.getElementById('transcribeProgressSection');
    progressSection.style.display = 'block';
    progressSection.classList.add('active');

    document.getElementById('transcribeStartBtn').disabled = true;
    document.getElementById('transcribeCancelBtn').style.display = 'inline-block';
    document.getElementById('transcribeProgressText').textContent = '准备中...';
    document.getElementById('transcribeProgressBar').style.width = '0%';
    document.getElementById('transcribeOutputLog').innerHTML = '';

    // Start elapsed timer
    if (serverStartTime) {
        transcribeStartTime = serverStartTime * 1000;
    } else {
        transcribeStartTime = Date.now();
    }
    updateTranscribeElapsedTime();
    transcribeElapsedTimer = setInterval(updateTranscribeElapsedTime, 1000);
}

/**
 * Hide progress section
 */
function hideTranscribeProgressSection() {
    const progressSection = document.getElementById('transcribeProgressSection');
    progressSection.classList.remove('active');

    document.getElementById('transcribeStartBtn').disabled = false;
    document.getElementById('transcribeCancelBtn').style.display = 'none';
    document.getElementById('transcribeProgressText').textContent = '已完成';
    document.getElementById('transcribeProgressBar').style.width = '100%';

    // Stop elapsed timer
    if (transcribeElapsedTimer) {
        clearInterval(transcribeElapsedTimer);
        transcribeElapsedTimer = null;
    }
}

/**
 * Update elapsed time display
 */
function updateTranscribeElapsedTime() {
    if (!transcribeStartTime) return;
    const elapsed = Math.floor((Date.now() - transcribeStartTime) / 1000);
    document.getElementById('transcribeElapsedTime').textContent = `已耗时: ${formatTime(elapsed)}`;
}

/**
 * Connect to SSE for progress updates
 */
function connectTranscribeSSE() {
    return new Promise((resolve) => {
        if (transcribeEventSource) {
            transcribeEventSource.close();
        }

        transcribeEventSource = new EventSource('/api/task/stream');

        transcribeEventSource.addEventListener('progress', (e) => {
            const data = JSON.parse(e.data);
            updateTranscribeProgress(data);
        });

        transcribeEventSource.addEventListener('transcribe_line', (e) => {
            const data = JSON.parse(e.data);
            appendTranscribeLogEvent('transcribe_line', data);
        });

        transcribeEventSource.addEventListener('transcribe_complete', (e) => {
            const data = JSON.parse(e.data);
            appendTranscribeLogEvent('info', { message: `转录完成: ${data.file}` });
        });

        transcribeEventSource.addEventListener('file_complete', (e) => {
            const data = JSON.parse(e.data);
            if (data.success) {
                appendTranscribeLogEvent('info', { message: `✓ 完成: ${data.file}` });
            } else {
                appendTranscribeLogEvent('error', { message: `✗ 失败: ${data.file} - ${data.message}` });
            }
        });

        transcribeEventSource.addEventListener('error', (e) => {
            if (e.data) {
                const data = JSON.parse(e.data);
                appendTranscribeLogEvent('error', data);
            }
        });

        transcribeEventSource.addEventListener('task_complete', (e) => {
            const data = JSON.parse(e.data);
            appendTranscribeLogEvent('info', { message: `任务完成! 成功: ${data.success_count}, 失败: ${data.fail_count}` });
            hideTranscribeProgressSection();
            transcribeEventSource.close();
            transcribeEventSource = null;
            scanTranscribeFiles();
        });

        transcribeEventSource.addEventListener('task_cancelled', () => {
            appendTranscribeLogEvent('info', { message: '任务已取消' });
            hideTranscribeProgressSection();
            transcribeEventSource.close();
            transcribeEventSource = null;
        });

        transcribeEventSource.onerror = (e) => {
            console.log('SSE connection error', e);
            appendTranscribeLogEvent('info', { message: 'SSE 连接断开，尝试重连...' });

            setTimeout(async () => {
                if (transcribeEventSource) {
                    transcribeEventSource.close();
                    transcribeEventSource = null;
                }

                const response = await fetch('/api/task/status');
                const status = await response.json();

                if (status.running) {
                    appendTranscribeLogEvent('info', { message: '重新连接...' });
                    connectTranscribeSSE();
                } else {
                    appendTranscribeLogEvent('info', { message: '任务已完成' });
                    hideTranscribeProgressSection();
                    scanTranscribeFiles();
                }
            }, 1000);
        };

        transcribeEventSource.onopen = () => {
            console.log('SSE connection opened');
            resolve();
        };
    });
}

/**
 * Update progress display
 */
function updateTranscribeProgress(data) {
    const progressText = document.getElementById('transcribeProgressText');
    const progressBar = document.getElementById('transcribeProgressBar');

    const phaseText = {
        'pending': '准备中',
        'transcribing': '正在转录',
        'embedding': '正在嵌入',
        'completed': '已完成',
        'failed': '失败',
    };

    const durationText = data.duration ? ` [${data.duration}]` : '';
    progressText.textContent = `(${data.current}/${data.total}) ${phaseText[data.phase] || data.phase}: ${data.file}${durationText}`;
    progressBar.style.width = `${(data.current / data.total) * 100}%`;
}

/**
 * Append log event to output log
 */
function appendTranscribeLogEvent(type, data) {
    const log = document.getElementById('transcribeOutputLog');
    const line = document.createElement('div');
    line.className = 'line';

    if (type === 'transcribe_line') {
        line.innerHTML = `<span class="time">${data.time}</span> <span class="text">${escapeHtml(data.text)}</span>`;
    } else if (type === 'error') {
        line.innerHTML = `<span class="error">${escapeHtml(data.message || data.file)}</span>`;
    } else if (type === 'info') {
        line.innerHTML = `<span class="info">${escapeHtml(data.message)}</span>`;
    }

    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}
