/**
 * Autocomplete component for path selection
 */

/**
 * Setup autocomplete functionality for a path input field
 * @param {string} inputId - ID of the input element
 * @param {string} dropdownId - ID of the dropdown element
 * @param {string} pathType - Type of path: 'directory' or 'file'
 */
function setupAutocomplete(inputId, dropdownId, pathType = 'directory') {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);

    if (!input || !dropdown) {
        console.warn(`Autocomplete setup failed: input or dropdown not found for ${inputId}`);
        return;
    }

    let debounceTimer = null;
    let currentFocus = -1;
    let suggestions = [];

    // Debounced search function
    async function searchPaths(prefix) {
        try {
            const response = await fetch(`/api/paths/search?prefix=${encodeURIComponent(prefix)}&path_type=${pathType}`);
            suggestions = await response.json();
            renderDropdown();
        } catch (error) {
            console.error('Path search error:', error);
            suggestions = [];
            renderDropdown();
        }
    }

    // Render dropdown with suggestions
    function renderDropdown() {
        if (suggestions.length === 0) {
            dropdown.innerHTML = '<div class="autocomplete-empty">No matching paths found</div>';
            dropdown.classList.remove('active');
            return;
        }

        dropdown.innerHTML = suggestions.map((path, index) =>
            `<div class="autocomplete-item" data-index="${index}">${escapeHtml(path)}</div>`
        ).join('');

        dropdown.classList.add('active');
        currentFocus = -1;

        // Add click handlers
        dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', function () {
                selectSuggestion(parseInt(this.dataset.index));
            });
        });
    }

    // Select a suggestion
    function selectSuggestion(index) {
        if (index >= 0 && index < suggestions.length) {
            input.value = suggestions[index];
            closeDropdown();
            input.focus();
        }
    }

    // Close dropdown
    function closeDropdown() {
        dropdown.classList.remove('active');
        currentFocus = -1;
    }

    // Highlight item
    function setActive(index) {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        items.forEach(item => item.classList.remove('highlighted'));
        if (index >= 0 && index < items.length) {
            items[index].classList.add('highlighted');
            items[index].scrollIntoView({ block: 'nearest' });
        }
    }

    // Input event handler
    input.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        const value = this.value.trim();

        if (value.length === 0) {
            closeDropdown();
            return;
        }

        debounceTimer = setTimeout(() => {
            searchPaths(value);
        }, 300);
    });

    // Keyboard navigation
    input.addEventListener('keydown', function (e) {
        const items = dropdown.querySelectorAll('.autocomplete-item');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentFocus++;
            if (currentFocus >= items.length) currentFocus = 0;
            setActive(currentFocus);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentFocus--;
            if (currentFocus < 0) currentFocus = items.length - 1;
            setActive(currentFocus);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (currentFocus >= 0) {
                selectSuggestion(currentFocus);
            }
        } else if (e.key === 'Escape') {
            closeDropdown();
        }
    });

    // Focus event - show common directories if empty
    input.addEventListener('focus', function () {
        if (this.value.trim().length === 0) {
            searchPaths('');
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function (e) {
        if (e.target !== input && !dropdown.contains(e.target)) {
            closeDropdown();
        }
    });
}

/**
 * Initialize autocomplete for all path inputs
 */
function initializeAutocomplete() {
    setupAutocomplete('sourceDir', 'sourceDirAutocomplete', 'directory');
    setupAutocomplete('lyricDir', 'lyricDirAutocomplete', 'directory');
    setupAutocomplete('outputDir', 'outputDirAutocomplete', 'directory');
    setupAutocomplete('coverPath', 'coverPathAutocomplete', 'file');

    // For merge tab
    setupAutocomplete('mergeSourceDir', 'mergeSourceDirAutocomplete', 'directory');
    setupAutocomplete('mergeOutputDir', 'mergeOutputDirAutocomplete', 'directory');
}
