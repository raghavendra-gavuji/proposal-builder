const API_BASE_URL = 'http://localhost:8000';

const state = {
    uploadedFile: null,
    proposalId: null,
    currentSlideIndex: -1, // -1 means no slide is selected
    totalSlides: 0,
    slidesData: []
};

const elements = {
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    fileStatus: document.getElementById('fileStatus'),
    generateBtn: document.getElementById('generateBtn'),
    applyChangesBtn: document.getElementById('applyChangesBtn'),
    downloadBtn: document.getElementById('downloadBtn'),
    editTextarea: document.getElementById('editTextarea'),
    statusMessages: document.getElementById('statusMessages'),
    slidesGrid: document.getElementById('slidesGrid'),
    previewWorkspace: document.getElementById('previewWorkspace'),
    mainSlideViewer: document.getElementById('mainSlideViewer'),
};

document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    loadSlideImages();
});

function initializeEventListeners() {
    elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
    elements.uploadArea.addEventListener('dragover', handleDragOver);
    elements.uploadArea.addEventListener('dragleave', handleDragLeave);
    elements.uploadArea.addEventListener('drop', handleDrop);
    elements.fileInput.addEventListener('change', handleFileSelect);
    
    elements.generateBtn.addEventListener('click', generateProposal);
    elements.applyChangesBtn.addEventListener('click', applyChanges);
    elements.downloadBtn.addEventListener('click', downloadProposal);
    
    document.addEventListener('keydown', handleKeyboardNavigation);
}

async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response;
    } catch (error) {
        console.error('API call failed:', error);
        throw error;
    }
}

/**
 * Load slide images from the slide_images folder
 * This function always loads whatever images are currently in the folder
 * (template images on startup, proposal images after generation)
 */
async function loadSlideImages() {
    try {
        console.log('📥 Loading slide images from slide_images folder...');
        
        const response = await apiCall('/api/template/slides');
        const data = await response.json();
        
        if (data.status === 'success') {
            state.totalSlides = data.total_slides;
            state.slidesData = data.slides;
            displaySlides(data.slides);
            console.log(`✅ Loaded ${data.total_slides} slide images`);
        } else {
            console.error('❌ Failed to load slides:', data.message);
            elements.slidesGrid.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--secondary-text);">${data.message || 'Could not load slides'}</div>`;
        }
    } catch (error) {
        console.error('❌ Error loading slide images:', error);
        elements.slidesGrid.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--secondary-text);">Could not load slides. Please ensure the backend is running.</div>`;
        showStatus('Failed to load slide images. Check backend.', 'error');
    }
}

function handleDragOver(e) {
    e.preventDefault();
    elements.uploadArea.classList.add('active');
}

function handleDragLeave(e) {
    elements.uploadArea.classList.remove('active');
}

function handleDrop(e) {
    e.preventDefault();
    elements.uploadArea.classList.remove('active');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload(files[0]);
    }
}

function handleFileSelect(e) {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
}

function handleFileUpload(file) {
    const validTypes = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel'
    ];
    
    if (validTypes.includes(file.type)) {
        state.uploadedFile = file;
        elements.fileStatus.innerHTML = createStatusHTML(`File uploaded: ${file.name}`, 'success');
        elements.generateBtn.disabled = false;
    } else {
        elements.fileStatus.innerHTML = createStatusHTML('Please upload a valid Excel file (.xlsx or .xls)', 'error');
    }
}

async function generateProposal() {
    if (!state.uploadedFile) return;
    
    setButtonLoading(elements.generateBtn, true, 'Generating...');
    showStatus('Creating proposal... This may take a few moments.', 'info');
    
    const formData = new FormData();
    formData.append('discovery_doc', state.uploadedFile);
    
    try {
        console.log('🚀 Sending request to create proposal...');
        
        const response = await apiCall('/api/proposals/create', { method: 'POST', body: formData });
        const data = await response.json();
        
        state.proposalId = data.proposal_id;
        
        setButtonLoading(elements.generateBtn, false, 'Generate Proposal');
        enableEditingControls();
        
        if (data.status === 'success') {
            showStatus('Proposal generated successfully! Reloading slides...', 'success');
            console.log(`✅ Proposal created with ID: ${state.proposalId}`);
            
            // Wait a moment to ensure images are written to disk, then reload
            setTimeout(async () => {
                await loadSlideImages();
                showStatus('Proposal slides loaded successfully!', 'success');
            }, 1000);
        } else {
            showStatus('Proposal creation failed. Please check logs.', 'error');
        }
        
    } catch (error) {
        console.error('❌ Error generating proposal:', error);
        setButtonLoading(elements.generateBtn, false, 'Generate Proposal');
        showStatus('Failed to generate proposal', 'error');
    }
}

async function applyChanges() {
    const changes = elements.editTextarea.value.trim();
    if (!changes || !state.proposalId) return;
    
    setButtonLoading(elements.applyChangesBtn, true, 'Applying...');
    showStatus('Applying changes... This may take a moment.', 'info');
    
    try {
        console.log('🔄 Applying changes to proposal...');
        
        await apiCall(`/api/proposals/${state.proposalId}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ changes })
        });
        
        setButtonLoading(elements.applyChangesBtn, false, 'Apply Changes');
        showStatus('Changes applied successfully! Reloading slides...', 'success');
        elements.editTextarea.value = '';
        
        console.log('✅ Changes applied, reloading slides...');
        
        // Wait a moment to ensure images are written to disk, then reload
        setTimeout(async () => {
            await loadSlideImages();
            showStatus('Updated slides loaded successfully!', 'success');
        }, 1000);
        
    } catch (error) {
        console.error('❌ Error applying changes:', error);
        setButtonLoading(elements.applyChangesBtn, false, 'Apply Changes');
        showStatus('Failed to apply changes', 'error');
    }
}

async function downloadProposal() {
    if (!state.proposalId) return;
    
    showStatus('Preparing download...', 'info');
    
    try {
        const response = await apiCall(`/api/proposals/${state.proposalId}/download`);
        const blob = await response.blob();
        
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `proposal_${state.proposalId}.pptx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showStatus('Download started!', 'success');
    } catch (error) {
        console.error('❌ Error downloading proposal:', error);
        showStatus('Failed to download proposal', 'error');
    }
}

function displaySlides(slides) {
    elements.slidesGrid.innerHTML = '';
    
    if (slides.length === 0) {
        elements.slidesGrid.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--secondary-text);">No slides to display</div>';
        return;
    }
    
    slides.forEach((slide, index) => {
        const slideCard = createSlideCard(slide, index);
        elements.slidesGrid.appendChild(slideCard);
    });
}

function createSlideCard(slide, index) {
    const slideCard = document.createElement('div');
    slideCard.className = 'slide-card';
    slideCard.dataset.slideIndex = index;
    
    let cardContent;
    if (slide.image_url) {
        // Add timestamp to prevent caching issues
        cardContent = `<img src="${API_BASE_URL}${slide.image_url}?t=${Date.now()}" alt="${slide.title}" class="slide-thumbnail">`;
    } else {
        const slideText = (slide.text_content || []).join(' ').substring(0, 80);
        cardContent = `<div class="slide-placeholder"><h3>${slide.title}</h3><p>${slideText}...</p></div>`;
    }

    slideCard.innerHTML = `
        <div class="slide-number">${slide.slide_number}</div>
        <div class="slide-content">${cardContent}</div>
    `;
    
    slideCard.addEventListener('click', () => showPresenterLayout(index));
    return slideCard;
}

function showPresenterLayout(slideIndex) {
    if (slideIndex < 0 || slideIndex >= state.totalSlides) return;

    elements.previewWorkspace.classList.add('presenter-view-active');

    const slide = state.slidesData[slideIndex];
    if (slide && slide.image_url) {
        // Add timestamp to prevent caching issues
        elements.mainSlideViewer.innerHTML = `<img src="${API_BASE_URL}${slide.image_url}?t=${Date.now()}" alt="Slide ${slide.slide_number}">`;
    } else {
        elements.mainSlideViewer.innerHTML = `<div class="viewer-placeholder"><p>Preview not available.</p></div>`;
    }

    document.querySelectorAll('.slide-card').forEach((card, index) => {
        card.classList.toggle('active', index === slideIndex);
    });

    state.currentSlideIndex = slideIndex;

    const activeCard = document.querySelector('.slide-card.active');
    if (activeCard) {
        activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function handleKeyboardNavigation(e) {
    if (state.currentSlideIndex === -1) return;

    let newIndex = state.currentSlideIndex;
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        newIndex = Math.max(0, state.currentSlideIndex - 1);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        newIndex = Math.min(state.totalSlides - 1, state.currentSlideIndex + 1);
    }

    if (newIndex !== state.currentSlideIndex) {
        showPresenterLayout(newIndex);
    }
}

function showStatus(message, type = 'info') {
    const statusClass = type === 'success' ? 'status-success' : type === 'error' ? 'status-error' : 'status-info';
    const icon = type === 'success' ? '<svg class="icon" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>' : type === 'error' ? '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="18" y1="6" x2="6" y2="18"></line></svg>' : '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    
    elements.statusMessages.innerHTML = `<div class="status-message ${statusClass}" style="stroke: currentColor; fill: none; stroke-width: 2;">${icon} ${message}</div>`;
    
    setTimeout(() => { elements.statusMessages.innerHTML = ''; }, 5000);
}

function createStatusHTML(message, type) {
    const statusClass = type === 'success' ? 'status-success' : 'status-error';
    const icon = type === 'success' ? '<svg class="icon" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>' : '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="18" y1="6" x2="6" y2="18"></line></svg>';
    
    return `<div class="status-message ${statusClass}" style="stroke: currentColor; fill: none; stroke-width: 2;">${icon} ${message}</div>`;
}

function setButtonLoading(button, isLoading, text) {
    button.disabled = isLoading;
    if (isLoading) {
        button.innerHTML = `<span class="loading"></span> ${text}`;
    } else {
        const iconHTML = button.id === 'generateBtn' ? '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>' : '';
        button.innerHTML = iconHTML ? `${iconHTML} ${text}` : text;
    }
}

function enableEditingControls() {
    elements.editTextarea.disabled = false;
    elements.applyChangesBtn.disabled = false;
    elements.downloadBtn.disabled = false;
}