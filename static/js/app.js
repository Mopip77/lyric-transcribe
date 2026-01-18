/**
 * Main Application Controller for Lyric Transcribe
 */

// Application state
let currentTab = 'merge';

/**
 * Initialize application
 */
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Lyric Transcribe initializing...');

    // Initialize components
    initializeModals();
    initializeAutocomplete();

    // Load configurations
    await loadModels();
    await loadConfig();
    loadMergeConfig();

    // Check if transcribe task is running
    await checkTranscribeTaskStatus();

    // Set default tab
    switchTab('merge');

    console.log('Lyric Transcribe initialized');
});

/**
 * Switch between tabs
 * @param {string} tabName - Name of the tab to switch to ('merge' or 'transcribe')
 */
function switchTab(tabName) {
    currentTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}Tab`).classList.add('active');
}

/**
 * Load available Whisper models
 */
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const models = await response.json();
        const select = document.getElementById('model');
        select.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
    } catch (error) {
        console.error('Error loading models:', error);
    }
}

/**
 * Load transcribe configuration
 */
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        document.getElementById('sourceDir').value = config.source_dir || '';
        document.getElementById('lyricDir').value = config.lyric_dir || '';
        document.getElementById('outputDir').value = config.output_dir || '';
        document.getElementById('coverPath').value = config.cover_path || '';
        document.getElementById('model').value = config.model || 'large-v3-turbo';
        document.getElementById('language').value = config.language || 'zh';
        document.getElementById('singerName').value = config.singer_name || '';
        document.getElementById('albumName').value = config.album_name || '';
        document.getElementById('prompt').value = config.prompt || '歌词 简体中文';
    } catch (error) {
        console.error('Error loading config:', error);
    }
}

/**
 * Save transcribe configuration
 */
async function saveConfig() {
    const config = {
        source_dir: document.getElementById('sourceDir').value,
        lyric_dir: document.getElementById('lyricDir').value,
        output_dir: document.getElementById('outputDir').value,
        cover_path: document.getElementById('coverPath').value,
        model: document.getElementById('model').value,
        language: document.getElementById('language').value,
        singer_name: document.getElementById('singerName').value,
        album_name: document.getElementById('albumName').value,
        prompt: document.getElementById('prompt').value,
    };

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });

        if (response.ok) {
            alert('配置已保存');
        } else {
            alert('保存配置失败');
        }
    } catch (error) {
        console.error('Error saving config:', error);
        alert('保存配置失败');
    }
}
