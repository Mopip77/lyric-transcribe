/**
 * Audio Merge Tab functionality
 */

// State for merge tab
let mergeFiles = [];
let mergeSelectedFiles = [];
let mergeEventSource = null;
let mergeElapsedTimer = null;
let mergeStartTime = null;

/**
 * Scan files for merging
 */
async function scanMergeFiles() {
    // First ensure config is loaded
    const configResponse = await fetch('/api/config');
    const config = await configResponse.json();

    if (!config.merge_source_dir) {
        alert('请先配置源音频目录');
        return;
    }

    // Temporarily update the source_dir to merge_source_dir for scanning
    const originalSourceDir = config.source_dir;
    config.source_dir = config.merge_source_dir;

    // Save temporarily
    await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
    });

    // Scan files
    const response = await fetch('/api/files');
    mergeFiles = await response.json();

    // Restore original source_dir
    config.source_dir = originalSourceDir;
    await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
    });

    renderMergeFileList();
}

/**
 * Render file list with size information
 */
function renderMergeFileList() {
    const container = document.getElementById('mergeFileListContainer');
    const actions = document.getElementById('mergeFileActions');

    if (mergeFiles.length === 0) {
        container.innerHTML = '<div class="empty-state">没有找到音频文件</div>';
        actions.style.display = 'none';
        document.getElementById('mergeOptionsSection').style.display = 'none';
        return;
    }

    container.innerHTML = `
        <div class="file-list">
            ${mergeFiles.map((file, index) => `
                <div class="file-item">
                    <input type="checkbox" id="merge-file-${index}">
                    <span class="file-name">${file.name}</span>
                    <span class="file-size">${formatFileSize(file.size_bytes)}</span>
                </div>
            `).join('')}
        </div>
    `;

    actions.style.display = 'flex';
    updateMergeSelectionCount();

    // Add event listeners
    mergeFiles.forEach((_, index) => {
        document.getElementById(`merge-file-${index}`).addEventListener('change', updateMergeSelectionCount);
    });
}

/**
 * Get selected files for merging
 */
function getSelectedMergeFiles() {
    return mergeFiles.filter((_, index) => {
        const checkbox = document.getElementById(`merge-file-${index}`);
        return checkbox && checkbox.checked;
    });
}

/**
 * Update selection count
 */
function updateMergeSelectionCount() {
    const count = getSelectedMergeFiles().length;
    document.getElementById('mergeSelectionCount').textContent = `已选择 ${count} 个文件`;

    // Show/hide merge options section based on selection
    const optionsSection = document.getElementById('mergeOptionsSection');
    if (count > 0) {
        optionsSection.style.display = 'block';
    } else {
        optionsSection.style.display = 'none';
    }
}

/**
 * Select all files
 */
function selectAllMerge() {
    mergeFiles.forEach((_, index) => {
        const checkbox = document.getElementById(`merge-file-${index}`);
        if (checkbox) checkbox.checked = true;
    });
    updateMergeSelectionCount();
}

/**
 * Deselect all files
 */
function selectNoneMerge() {
    mergeFiles.forEach((_, index) => {
        const checkbox = document.getElementById(`merge-file-${index}`);
        if (checkbox) checkbox.checked = false;
    });
    updateMergeSelectionCount();
}

/**
 * Inverse selection
 */
function selectInverseMerge() {
    mergeFiles.forEach((_, index) => {
        const checkbox = document.getElementById(`merge-file-${index}`);
        if (checkbox) checkbox.checked = !checkbox.checked;
    });
    updateMergeSelectionCount();
}

/**
 * Open order adjustment modal
 */
function openMergeOrderModal() {
    const selectedFiles = getSelectedMergeFiles();

    if (selectedFiles.length < 2) {
        alert('请至少选择 2 个文件进行合并');
        return;
    }

    // Sort by filename initially
    mergeSelectedFiles = selectedFiles.sort((a, b) => a.name.localeCompare(b.name));

    renderOrderList();
    openModal('mergeOrderModal');
}

/**
 * Render draggable order list
 */
function renderOrderList() {
    const orderList = document.getElementById('mergeOrderList');

    orderList.innerHTML = mergeSelectedFiles.map((file, index) => `
        <div class="draggable-item" draggable="true" data-index="${index}">
            <span class="drag-handle">≡</span>
            <span class="item-index">${index + 1}.</span>
            <span class="item-name">${file.name}</span>
            <span class="item-info">(估计大小)</span>
        </div>
    `).join('');

    // Setup drag and drop
    setupDragAndDrop();
}

/**
 * Setup drag and drop functionality
 */
function setupDragAndDrop() {
    const items = document.querySelectorAll('.draggable-item');
    let draggedItem = null;

    items.forEach(item => {
        item.addEventListener('dragstart', function (e) {
            draggedItem = this;
            this.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        item.addEventListener('dragend', function () {
            this.classList.remove('dragging');
            items.forEach(i => i.classList.remove('drag-over'));
        });

        item.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            if (this !== draggedItem) {
                this.classList.add('drag-over');
            }
        });

        item.addEventListener('dragleave', function () {
            this.classList.remove('drag-over');
        });

        item.addEventListener('drop', function (e) {
            e.preventDefault();
            e.stopPropagation();

            if (this !== draggedItem) {
                const draggedIndex = parseInt(draggedItem.dataset.index);
                const targetIndex = parseInt(this.dataset.index);

                // Swap items in array
                const temp = mergeSelectedFiles[draggedIndex];
                mergeSelectedFiles[draggedIndex] = mergeSelectedFiles[targetIndex];
                mergeSelectedFiles[targetIndex] = temp;

                // Re-render
                renderOrderList();
            }

            this.classList.remove('drag-over');
        });
    });
}

/**
 * Confirm merge with file conflict check
 */
async function confirmMerge() {
    const outputName = document.getElementById('mergeOutputName').value.trim();
    const deleteSources = document.getElementById('mergeDeleteSources').checked;

    if (!outputName) {
        alert('请输入合并文件名');
        return;
    }

    // Ensure .wav extension
    const finalOutputName = outputName.endsWith('.wav') ? outputName : `${outputName}.wav`;

    // Check if file exists
    const outputDir = document.getElementById('mergeOutputDir').value;
    if (!outputDir) {
        alert('请先配置输出目录');
        return;
    }

    try {
        const checkResponse = await fetch(`/api/audio/check-exists?filename=${encodeURIComponent(finalOutputName)}`);
        const checkData = await checkResponse.json();

        if (checkData.exists) {
            // Show conflict dialog
            showFileConflictDialog(finalOutputName, deleteSources);
        } else {
            // Proceed with merge
            startMerge(finalOutputName, deleteSources, false);
        }
    } catch (error) {
        console.error('Error checking file existence:', error);
        // Proceed anyway
        startMerge(finalOutputName, deleteSources, false);
    }
}

/**
 * Show file conflict dialog
 */
function showFileConflictDialog(filename, deleteSources) {
    closeModal('mergeOrderModal');

    document.getElementById('conflictFileName').textContent = filename;
    openModal('fileConflictModal');

    // Setup button handlers
    document.getElementById('overwriteBtn').onclick = () => {
        closeModal('fileConflictModal');
        startMerge(filename, deleteSources, true);
    };

    document.getElementById('renameBtn').onclick = () => {
        closeModal('fileConflictModal');
        const newFilename = generateUniqueFilename(filename);
        startMerge(newFilename, deleteSources, false);
    };

    document.getElementById('cancelMergeBtn').onclick = () => {
        closeModal('fileConflictModal');
        // Reopen order modal
        openModal('mergeOrderModal');
    };
}

/**
 * Start the merge process
 */
async function startMerge(outputName, deleteSources, overwrite) {
    closeModal('mergeOrderModal');
    closeModal('fileConflictModal');

    // Get config to use merge_output_dir
    const configResponse = await fetch('/api/config');
    const config = await configResponse.json();

    if (!config.merge_output_dir) {
        alert('请先配置输出目录');
        return;
    }

    // Show progress
    showMergeProgressSection();

    // Connect SSE
    await connectMergeSSE();

    // Start merge task
    const fileNames = mergeSelectedFiles.map(f => f.name);

    const response = await fetch('/api/audio/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            files: fileNames,
            output_name: outputName,
            delete_sources: deleteSources,
            overwrite: overwrite
        }),
    });

    if (!response.ok) {
        const error = await response.json();
        alert(error.detail || '启动合并任务失败');
        hideMergeProgressSection();
        if (mergeEventSource) {
            mergeEventSource.close();
            mergeEventSource = null;
        }
        return;
    }
}

/**
 * Show merge progress section
 */
function showMergeProgressSection() {
    const progressSection = document.getElementById('mergeProgressSection');
    progressSection.style.display = 'block';
    progressSection.classList.add('active');

    document.getElementById('mergeProgressText').textContent = '准备合并...';
    document.getElementById('mergeProgressBar').style.width = '0%';
    document.getElementById('mergeOutputLog').innerHTML = '';

    mergeStartTime = Date.now();
    updateMergeElapsedTime();
    mergeElapsedTimer = setInterval(updateMergeElapsedTime, 1000);
}

/**
 * Hide merge progress section
 */
function hideMergeProgressSection() {
    const progressSection = document.getElementById('mergeProgressSection');
    progressSection.style.display = 'none';
    progressSection.classList.remove('active');

    if (mergeElapsedTimer) {
        clearInterval(mergeElapsedTimer);
        mergeElapsedTimer = null;
    }
}

/**
 * Update elapsed time
 */
function updateMergeElapsedTime() {
    if (!mergeStartTime) return;
    const elapsed = Math.floor((Date.now() - mergeStartTime) / 1000);
    document.getElementById('mergeElapsedTime').textContent = `已耗时: ${formatTime(elapsed)}`;
}

/**
 * Connect to merge SSE stream
 */
function connectMergeSSE() {
    return new Promise((resolve) => {
        if (mergeEventSource) {
            mergeEventSource.close();
        }

        mergeEventSource = new EventSource('/api/audio/merge/stream');

        mergeEventSource.addEventListener('merge_start', (e) => {
            const data = JSON.parse(e.data);
            appendMergeLogEvent('info', { message: `开始合并: ${data.file_count} 个文件` });
        });

        mergeEventSource.addEventListener('merge_progress', (e) => {
            const data = JSON.parse(e.data);
            updateMergeProgress(data);
        });

        mergeEventSource.addEventListener('merge_complete', (e) => {
            const data = JSON.parse(e.data);
            appendMergeLogEvent('info', { message: `✓ 合并完成: ${data.output_file}` });
            hideMergeProgressSection();
            mergeEventSource.close();
            mergeEventSource = null;

            // Refresh file list
            scanMergeFiles();
            alert('音频合并完成！');
        });

        mergeEventSource.addEventListener('merge_error', (e) => {
            const data = JSON.parse(e.data);
            appendMergeLogEvent('error', { message: `✗ 合并失败: ${data.message}` });
            hideMergeProgressSection();
            mergeEventSource.close();
            mergeEventSource = null;
        });

        mergeEventSource.onerror = () => {
            console.log('Merge SSE connection error');
            setTimeout(async () => {
                if (mergeEventSource) {
                    mergeEventSource.close();
                    mergeEventSource = null;
                }
            }, 1000);
        };

        mergeEventSource.onopen = () => {
            console.log('Merge SSE connection opened');
            resolve();
        };
    });
}

/**
 * Update merge progress
 */
function updateMergeProgress(data) {
    const progressText = document.getElementById('mergeProgressText');
    const progressBar = document.getElementById('mergeProgressBar');

    progressText.textContent = data.message || '正在合并...';
    progressBar.style.width = `${data.percentage || 0}%`;
}

/**
 * Append log event
 */
function appendMergeLogEvent(type, data) {
    const log = document.getElementById('mergeOutputLog');
    const line = document.createElement('div');
    line.className = 'line';

    if (type === 'error') {
        line.innerHTML = `<span class="error">${escapeHtml(data.message)}</span>`;
    } else if (type === 'info') {
        line.innerHTML = `<span class="info">${escapeHtml(data.message)}</span>`;
    }

    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}

/**
 * Save merge config to backend
 */
async function saveMergeConfig() {
    const mergeSourceDir = document.getElementById('mergeSourceDir').value;
    const mergeOutputDir = document.getElementById('mergeOutputDir').value;

    // Load existing config
    const response = await fetch('/api/config');
    const config = await response.json();

    // Update merge fields
    config.merge_source_dir = mergeSourceDir;
    config.merge_output_dir = mergeOutputDir;

    // Save to backend
    try {
        const saveResponse = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });

        if (saveResponse.ok) {
            alert('合并配置已保存');
        } else {
            alert('保存配置失败');
        }
    } catch (error) {
        console.error('Error saving merge config:', error);
        alert('保存配置失败');
    }
}

/**
 * Load merge config from backend
 */
async function loadMergeConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        document.getElementById('mergeSourceDir').value = config.merge_source_dir || '';
        document.getElementById('mergeOutputDir').value = config.merge_output_dir || '';
    } catch (error) {
        console.error('Error loading merge config:', error);
    }
}
