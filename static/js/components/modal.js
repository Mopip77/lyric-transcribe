/**
 * Modal component for dialogs and popups
 */

/**
 * Open a modal by ID
 * @param {string} modalId - ID of the modal element
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        // Prevent body scroll when modal is open
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close a modal by ID
 * @param {string} modalId - ID of the modal element
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        // Restore body scroll
        document.body.style.overflow = '';
    }
}

/**
 * Close modal when clicking outside the modal content
 * @param {Event} event - Click event
 * @param {string} modalId - ID of the modal element
 */
function closeModalOnOutsideClick(event, modalId) {
    const modal = document.getElementById(modalId);
    if (event.target === modal) {
        closeModal(modalId);
    }
}

/**
 * Initialize modal close handlers
 */
function initializeModals() {
    // Close modals when clicking on overlay
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal(modal.id);
            }
        });
    });

    // Close modals with Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.active').forEach(modal => {
                closeModal(modal.id);
            });
        }
    });
}
