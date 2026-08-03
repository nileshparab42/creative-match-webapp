// Inject the sidebar into the page
// Call renderSidebar(activeView) on each page, where activeView matches one of the nav keys
function renderSidebar(activeView) {
  const sidebarHTML = `
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-mark">Parul University</div>
      <div class="logo-name">Creative Match</div>
    </div>

    <div class="nav-section">
      <div class="nav-label">Pipeline</div>
      <a class="nav-item ${activeView === 'dashboard' ? 'active' : ''}" href="/home">
        <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
          <rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
        </svg>
        Dashboard
      </a>
      <a class="nav-item ${activeView === 'run' ? 'active' : ''}" href="/run">
        <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <polygon points="4,2 14,8 4,14"/>
        </svg>
        Run pipeline
      </a>
    </div>

    <div class="nav-section">
      <div class="nav-label">Results</div>
      <a class="nav-item ${activeView === 'audiences' ? 'active' : ''}" href="/audiences">
        <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="1" y="2" width="14" height="12" rx="1.5"/><path d="M4 6h8M4 9h5"/>
        </svg>
        Recommendation report
      </a>
    </div>

    <div class="nav-section">
      <div class="nav-label">Account</div>
      <a class="nav-item ${activeView === 'settings' ? 'active' : ''}" href="/settings">
        <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8" cy="8" r="2.5"/>
          <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.22 3.22l1.41 1.41M11.37 11.37l1.41 1.41M3.22 12.78l1.41-1.41M11.37 4.63l1.41-1.41"/>
        </svg>
        Account settings
      </a>
    </div>

    <div class="sidebar-footer">
      <div class="client-chip">
        <div class="client-avatar">C</div>
        <div class="client-info">
          <div class="client-name">client@lsdigital.com</div>
          <div class="client-role">Pipeline user</div>
        </div>
      </div>
    </div>
  </aside>`;

  document.body.insertAdjacentHTML('afterbegin', sidebarHTML);
}

// Creative modal HTML (shared across pages that need it)
function renderCreativeModal() {
  const modalHTML = `
  <div class="modal-overlay" id="creativeModal" style="display:none;">
    <div class="modal" style="width:560px;">
      <div class="modal-tag">Creative selection</div>
      <div class="modal-title">Select creatives for this run</div>
      <div class="modal-sub" style="margin-bottom:16px;">
        Choose which assets from your GAds account to include. Creatives marked <span style="color:var(--danger);font-family:var(--mono);font-size:11px;">no data</span> don't have enough click history yet and will be excluded automatically.
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <span style="font-size:12px;color:var(--text-muted);">Fetched from GAds · last synced 06:00 AM</span>
        <button class="btn btn-sm">↻ Refresh from GAds</button>
      </div>
      <div class="creative-grid" id="creativeGrid"></div>
      <div class="modal-footer">
        <span style="font-family:var(--mono);font-size:11px;color:var(--text-muted);margin-right:auto;" id="selectedCount">0 selected</span>
        <button class="btn" onclick="closeCreativeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="confirmCreatives()">Confirm selection →</button>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML('afterbegin', modalHTML);
}
