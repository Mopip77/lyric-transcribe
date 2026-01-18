/**
 * Utility functions for Lyric Transcribe
 */

/**
 * Escape HTML special characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format seconds to MM:SS format
 * @param {number} seconds - Seconds to format
 * @returns {string} Formatted time string
 */
function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes} 分 ${secs.toString().padStart(2, '0')} 秒`;
}

/**
 * Format file size in bytes to human-readable format
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * Generate a unique filename if file already exists
 * @param {string} filename - Original filename
 * @param {number} suffix - Suffix number (default: 1)
 * @returns {string} New filename with suffix
 */
function generateUniqueFilename(filename, suffix = 1) {
    const lastDot = filename.lastIndexOf('.');
    if (lastDot === -1) {
        return `${filename}_${suffix}`;
    }
    const name = filename.substring(0, lastDot);
    const ext = filename.substring(lastDot);
    return `${name}_${suffix}${ext}`;
}
