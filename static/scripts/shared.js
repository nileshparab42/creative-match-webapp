const campaigns = JSON.parse(
    document.getElementById('campaigns-data').textContent
);

const creatives = campaigns.map(campaign => ({
    id: String(campaign.id),
    name: campaign.name,
    type: campaign.type,
    images: 1,                  // change if you have image count
    selected: true,             // default value
    hasData: !!campaign.image,  // true if image exists
    image: campaign.image
}));


const reportData = [
  { segment: 'High intent — mobile',   size: 24100, creative: 'Admission Deadline — Green',  asset_id: '803653449091', type: 'Demand Gen', score: 0.91, budget: null, bidding: null, ga4: 'Pushed' },
  { segment: 'Returners — desktop',    size: 18700, creative: 'Online M.Sc. — CTA Overlay',  asset_id: '803653449073', type: 'Demand Gen', score: 0.84, budget: null, bidding: null, ga4: 'Pushed' },
  { segment: 'New visitors — south',   size: 16200, creative: 'Programme Banner — Blue',      asset_id: '803653449037', type: 'Display',    score: 0.77, budget: null, bidding: null, ga4: 'Pushed' },
  { segment: 'Mid funnel — engaged',   size: 14900, creative: 'Responsive Display — Batch',   asset_id: '803653448854', type: 'Display',    score: 0.71, budget: null, bidding: null, ga4: 'Pushed' },
  { segment: 'Low freq — weekday',     size: 10300, creative: 'Scholarship Offer — July',     asset_id: '803537801273', type: 'Demand Gen', score: 0.54, budget: null, bidding: null, ga4: 'Pending' },
];

// ── SHARED UTILITIES ──
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'copied!';
    btn.style.color = 'var(--success)';
    setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 1500);
  });
}

// function downloadCSV() {
//   const headers = ['Segment','Audience size','Recommended creative','Creative asset ID','Campaign type','Conv. score','Suggested budget (INR)','Bidding strategy','GA4 push status'];
//   const rows = reportData.map(r => [
//     r.segment, r.size, r.creative, r.asset_id, r.type,
//     r.score, r.budget || '—', r.bidding || '—', r.ga4
//   ]);
//   const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n');
//   const blob = new Blob([csv], { type: 'text/csv' });
//   const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
//   a.download = `creative_recommendation_report_2026-06-04.csv`; a.click();
// }

// function downloadJSON() {
//   const blob = new Blob([JSON.stringify({ generated: '2026-06-04T03:14:00', client: 'client@lsdigital.com', segments: reportData }, null, 2)], { type: 'application/json' });
//   const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
//   a.download = `creative_recommendation_report_2026-06-04.json`; a.click();
// }

// ── CREATIVE MODAL ──
function openCreativeModal() {
  const grid = document.getElementById('creativeGrid');
  if (!grid) return;
  grid.innerHTML = creatives.map((c, i) => `
    <div class="creative-tile ${c.selected && c.hasData ? 'selected' : ''} ${!c.hasData ? 'no-data' : ''}"
         onclick="${c.hasData ? 'toggleCreative(' + i + ')' : ''}">
      <div class="tile-check">✓</div>
      <div class="tile-thumb">
          <img src="https://mir-s3-cdn-cf.behance.net/project_modules/1400/ac51bc127563551.61443f1f80889.jpg" alt="IMG">
      </div>
      <div class="tile-name">${c.name.length > 22 ? c.name.slice(0,22)+'…' : c.name}</div>
      <div class="tile-type">${c.id}</div>
      ${!c.hasData ? '<div class="tile-nodata">no data · excluded</div>' : ''}
    </div>
  `).join('');
  updateSelectedCount();
  document.getElementById('creativeModal').style.display = 'flex';
}

function toggleCreative(i) {
  if (!creatives[i].hasData) return;
  creatives[i].selected = !creatives[i].selected;
  const tiles = document.querySelectorAll('.creative-tile');
  tiles[i].classList.toggle('selected');
  updateSelectedCount();
}

function updateSelectedCount() {
  const n = creatives.filter(c => c.selected && c.hasData).length;
  const el = document.getElementById('selectedCount');
  if (el) el.textContent = n + ' selected';
}

function closeCreativeModal() {
  document.getElementById('creativeModal').style.display = 'none';
}

function confirmCreatives() {
  const n = creatives.filter(c => c.selected && c.hasData).length;
  const el = document.getElementById('runCreativeCount');
  if (el) el.textContent = n + ' creatives selected';
  closeCreativeModal();
}
