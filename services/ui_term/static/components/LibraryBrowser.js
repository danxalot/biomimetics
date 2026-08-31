/**
 * LibraryBrowser - File Tree Navigation Component
 * FIXED: Interactive file browser with directory expansion
 */
class LibraryBrowser extends BaseComponent {
    constructor(containerId = '#library-panel') {
        super(containerId);
        this.state = {
            currentPath: '/shared_storage',
            expandedDirs: new Set(),
            files: [],
            selectedFile: null
        };

        // Load initial file tree
        this.loadFiles();
    }

    template() {
        return `
            <div class="library-container">
                <div class="library-header">
                    <span>Library & Knowledge</span>
                    <button class="btn-tiny" id="refreshFiles">↻</button>
                </div>
                
                <div class="library-path">
                    <input type="text" id="pathInput" value="${this.state.currentPath}" />
                    <button class="btn-tiny" id="goPath">Go</button>
                </div>
                
                <div class="file-tree" id="fileTree">
                    ${this.renderFileTree()}
                </div>
            </div>
        `;
    }

    renderFileTree() {
        if (!this.state.files.length) {
            return '<div class="placeholder">Loading files...</div>';
        }

        return this.state.files.map(file => this.renderFileNode(file, 0)).join('');
    }

    renderFileNode(file, depth) {
        const indent = depth * 20;
        const isExpanded = this.state.expandedDirs.has(file.path);
        const icon = file.is_dir ? (isExpanded ? '📂' : '📁') : this.getFileIcon(file.name);

        let html = `
            <div class="file-item" style="padding-left: ${indent}px" data-path="${file.path}">
                ${file.is_dir ? `<span class="expand-icon">${isExpanded ? '▼' : '▶'}</span>` : ''}
                <span class="file-icon">${icon}</span>
                <span class="file-name">${file.name}</span>
            </div>
        `;

        // Render children if expanded
        if (file.is_dir && isExpanded && file.children) {
            html += file.children.map(child => this.renderFileNode(child, depth + 1)).join('');
        }

        return html;
    }

    getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const iconMap = {
            'md': '📝',
            'py': '🐍',
            'js': '📜',
            'json': '{}',
            'yml': '⚙️',
            'yaml': '⚙️',
            'txt': '📄',
            'png': '🖼️',
            'jpg': '🖼️',
            'gif': '🖼️'
        };
        return iconMap[ext] || '📄';
    }

    attachEventListeners() {
        // File/folder click
        const fileItems = this.container.querySelectorAll('.file-item');
        fileItems.forEach(item => {
            item.addEventListener('click', (e) => {
                const path = item.dataset.path;
                const file = this.findFile(path);

                if (file.is_dir) {
                    this.toggleDirectory(path);
                } else {
                    this.openFile(path);
                }
            });
        });

        // Refresh button
        const refreshBtn = this.container.querySelector('#refreshFiles');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadFiles());
        }

        // Path navigation
        const goBtn = this.container.querySelector('#goPath');
        if (goBtn) {
            goBtn.addEventListener('click', () => {
                const pathInput = this.container.querySelector('#pathInput');
                this.state.currentPath = pathInput.value;
                this.loadFiles();
            });
        }
    }

    async loadFiles() {
        try {
            // In Puter.js version, this will use puter.fs.readdir()
            // For now, use backend API
            const response = await fetch(`/api/files/list?path=${encodeURIComponent(this.state.currentPath)}`);
            const data = await response.json();

            this.setState({ files: data.files || [] });
        } catch (e) {
            console.error('Failed to load files:', e);

            // Fallback to mock data for development
            this.setState({
                files: this.getMockFiles()
            });
        }
    }

    getMockFiles() {
        return [
            {
                name: 'shared_storage',
                path: '/shared_storage',
                is_dir: true,
                children: [
                    { name: 'project_brief.md', path: '/shared_storage/project_brief.md', is_dir: false },
                    { name: 'architecture.png', path: '/shared_storage/architecture.png', is_dir: false }
                ]
            },
            {
                name: 'mcp_skills',
                path: '/mcp_skills',
                is_dir: true,
                children: [
                    { name: 'ARCA_CONFIG.md', path: '/mcp_skills/ARCA_CONFIG.md', is_dir: false }
                ]
            }
        ];
    }

    toggleDirectory(path) {
        if (this.state.expandedDirs.has(path)) {
            this.state.expandedDirs.delete(path);
        } else {
            this.state.expandedDirs.add(path);
        }
        this.render();
        this.attachEventListeners();
    }

    async openFile(path) {
        this.state.selectedFile = path;

        // Emit event for other components to handle
        this.emit('file-opened', { path });

        // Also send to backend to get content
        try {
            const response = await fetch(`/api/files/content?path=${encodeURIComponent(path)}`);
            const data = await response.json();

            this.emit('file-content', { path, content: data.content });
        } catch (e) {
            console.error('Failed to load file content:', e);
        }
    }

    findFile(path, files = this.state.files) {
        for (const file of files) {
            if (file.path === path) return file;
            if (file.children) {
                const found = this.findFile(path, file.children);
                if (found) return found;
            }
        }
        return null;
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LibraryBrowser;
}
