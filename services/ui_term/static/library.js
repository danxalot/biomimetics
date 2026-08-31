/**
 * ARCA Library & Knowledge Browser - Frontend JavaScript
 * Handles file tree rendering, search, drag-drop, and file operations
 */

// State
let currentPath = '/';
let fileTree = {};
let selectedNode = null;

// Initialize library browser
async function initLibraryBrowser() {
    await loadFileTree();
    setupEventListeners();
}

// Load and render file tree
async function loadFileTree(path = '') {
    try {
        currentPath = path;

        // Show loading state
        const container = document.getElementById('libraryFileTree');
        if (path === '') { // Only clear on root load to avoid flickering
            container.innerHTML = '<div class="loading-spinner">Loading...</div>';
        }

        console.log(`[Library] Fetching path: '${path}'`);
        const response = await fetch(`/api/library/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        console.log("[Library] API Response:", data);

        if (data.error) {
            console.error("[Library] API Error:", data.error);
            showToast(data.error, 'error');
            return;
        }

        fileTree = data;
        renderFileTree(data);
    } catch (error) {
        console.error("[Library] Network/Parse Error:", error);
        showToast('Failed to load file tree', 'error');
    }
}

// Render file tree HTML
function renderFileTree(data) {
    const container = document.getElementById('libraryFileTree');
    container.innerHTML = '';

    // Check if we have files
    if (!data.files || data.files.length === 0) {
        container.innerHTML = '<div class="empty-state">No files found</div>';
        return;
    }

    // Render directory contents
    const ul = document.createElement('ul');
    ul.className = 'file-tree';

    // Add '..' for Parent Directory if not root
    if (currentPath && currentPath !== '/' && currentPath !== '.') {
        const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/';
        const upNode = document.createElement('li');
        upNode.className = 'tree-node directory up-dir';
        upNode.innerHTML = `<span class="tree-icon">📂</span><span class="tree-label">..</span>`;
        upNode.onclick = (e) => { e.stopPropagation(); loadFileTree(parentPath); };
        ul.appendChild(upNode);
    }

    // Folders first
    data.files.filter(item => item.type === 'directory')
        .forEach(item => ul.appendChild(createTreeNode(item)));

    // Then files
    data.files.filter(item => item.type === 'file')
        .forEach(item => ul.appendChild(createTreeNode(item)));

    container.appendChild(ul);
}

// Create tree node element
function createTreeNode(item) {
    const li = document.createElement('li');
    li.className = `tree-node ${item.type}`;
    li.dataset.path = item.path; // API returns relative path from root
    li.dataset.type = item.type;

    const icon = item.type === 'directory' ? '📁' : '📄';
    const size = item.size ? ` (${formatFileSize(item.size)})` : '';

    // Safety check for path
    const displayPath = item.path === '.' ? '/' : item.path;

    li.innerHTML = `
        <span class="tree-icon">${icon}</span>
        <span class="tree-label" title="${displayPath}">${item.name}${size}</span>
    `;

    // Click handler
    li.addEventListener('click', (e) => {
        e.stopPropagation();
        handleNodeClick(item, li);
    });

    // Context menu
    li.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showContextMenu(e, item);
    });

    return li;
}

// Handle node click
function handleNodeClick(item, element) {
    // Clear previous selection
    document.querySelectorAll('.tree-node.selected').forEach(el => {
        el.classList.remove('selected');
    });

    element.classList.add('selected');
    selectedNode = item;

    if (item.type === 'directory') {
        loadFileTree(item.path);
    } else {
        viewDocument(item.path);
    }
}

// Search files
async function searchFiles() {
    const query = document.getElementById('librarySearch').value.trim();
    if (!query) {
        loadFileTree();
        return;
    }

    try {
        const response = await fetch(`/api/library/search?query=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        renderSearchResults(data.results);
    } catch (error) {
        showToast('Search failed', 'error');
        console.error(error);
    }
}

// Render search results
function renderSearchResults(results) {
    const container = document.getElementById('libraryFileTree');
    container.innerHTML = `<div class="search-results-header">Found ${results.length} result(s)</div>`;

    const ul = document.createElement('ul');
    ul.className = 'file-tree search-results';

    results.forEach(item => ul.appendChild(createTreeNode(item)));
    container.appendChild(ul);
}

// Create new folder
async function createFolder() {
    const name = prompt('Enter folder name:');
    if (!name) return;

    try {
        const response = await fetch('/api/library/folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentPath, name })
        });

        const data = await response.json();
        if (data.error) {
            showToast(data.error, 'error');
        } else {
            showToast('Folder created', 'success');
            loadFileTree(currentPath);
        }
    } catch (error) {
        showToast('Failed to create folder', 'error');
    }
}

// Upload files
async function uploadFiles(files) {
    const formData = new FormData();
    formData.append('path', currentPath);

    Array.from(files).forEach(file => {
        formData.append('files', file);
    });

    try {
        const response = await fetch('/api/library/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (data.error) {
            showToast(data.error, 'error');
        } else {
            showToast(`Uploaded ${data.uploaded.length} file(s)`, 'success');
            loadFileTree(currentPath);
        }
    } catch (error) {
        showToast('Upload failed', 'error');
    }
}

// Delete file/folder
async function deleteItem(path) {
    if (!confirm(`Delete ${path}?`)) return;

    try {
        const response = await fetch(`/api/library/delete?path=${encodeURIComponent(path)}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (data.error) {
            showToast(data.error, 'error');
        } else {
            showToast('Deleted successfully', 'success');
            loadFileTree(currentPath);
        }
    } catch (error) {
        showToast('Delete failed', 'error');
    }
}

// Copy path to clipboard
function copyPath(path) {
    navigator.clipboard.writeText(path).then(() => {
        showToast('Path copied to clipboard', 'success');
    });
}

// Show context menu
function showContextMenu(event, item) {
    // Remove existing menu
    const existingMenu = document.querySelector('.context-menu');
    if (existingMenu) existingMenu.remove();

    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.left = event.pageX + 'px';
    menu.style.top = event.pageY + 'px';

    const menuItems = [
        { label: 'Copy Path', action: () => copyPath(item.path) },
        { label: 'Delete', action: () => deleteItem(item.path) }
    ];

    if (item.type === 'file') {
        menuItems.unshift({ label: 'Download', action: () => downloadFile(item.path) });
    }

    menuItems.forEach(({ label, action }) => {
        const menuItem = document.createElement('div');
        menuItem.className = 'context-menu-item';
        menuItem.textContent = label;
        menuItem.addEventListener('click', () => {
            action();
            menu.remove();
        });
        menu.appendChild(menuItem);
    });

    document.body.appendChild(menu);

    // Close menu on click outside
    setTimeout(() => {
        document.addEventListener('click', () => menu.remove(), { once: true });
    }, 0);
}

// Download file
function downloadFile(path) {
    window.open(`/api/library/download/${encodeURIComponent(path)}`, '_blank');
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Format file size
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Setup event listeners
function setupEventListeners() {
    // Search
    const searchInput = document.getElementById('librarySearch');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(searchFiles, 300));
    }

    // Toolbar buttons
    const newFolderBtn = document.getElementById('newFolderBtn');
    if (newFolderBtn) {
        newFolderBtn.onclick = createFolder; // Direct assignment is safer for re-runs
    }

    const upBtn = document.getElementById('upDirBtn');
    if (upBtn) {
        upBtn.onclick = () => {
            if (!currentPath || currentPath === '' || currentPath === '/') return;
            const parent = currentPath.split('/').slice(0, -1).join('/') || '/';
            loadFileTree(parent);
        };
    }

    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) {
        uploadBtn.onclick = () => {
            const input = document.createElement('input');
            input.type = 'file';
            input.multiple = true;
            input.onchange = (e) => uploadFiles(e.target.files);
            input.click();
        };
    }

    const refreshBtn = document.getElementById('refreshBtn'); // Was missing definition
    if (refreshBtn) {
        refreshBtn.onclick = () => loadFileTree(currentPath);
    }

    const pinBtn = document.getElementById('pinDirBtn');
    if (pinBtn) {
        pinBtn.addEventListener('click', async () => {
            // Pin logic
            try {
                const response = await fetch(`/api/library/pin?path=${encodeURIComponent(currentPath)}`, { method: 'POST' });
                const res = await response.json();
                showToast(res.status === 'pinned' ? 'Directory Pinned 📌' : 'Failed to pin', 'success');
            } catch (e) { showToast('Pin failed', 'error'); }
        });
    }

    // Drag and drop
    const dropZone = document.getElementById('libraryFileTree');
    const overlay = document.getElementById('dragDropOverlay');

    if (dropZone && overlay) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            overlay.classList.remove('hidden');
        });

        dropZone.addEventListener('dragleave', (e) => {
            if (e.target === dropZone) {
                overlay.classList.add('hidden');
            }
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            overlay.classList.add('hidden');
            uploadFiles(e.dataTransfer.files);
        });
    }
}

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLibraryBrowser);
} else {
    initLibraryBrowser();
}
