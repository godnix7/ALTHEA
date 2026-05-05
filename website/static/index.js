/* ---------- SAFE NAVIGATION HELPERS ---------- */

async function safeNavigate(url) {
  try {
    // Try a HEAD request to see if resource exists.
    const resp = await fetch(url, { method: 'HEAD' });
    if (resp.ok) {
      // Resource exists — navigate.
      window.location.href = url;
    } else {
      appendMessage(`Sorry — "${url}" was not found on the server (HTTP ${resp.status}).`, 'bot');
    }
  } catch (err) {
    // Network or CORS — fall back to an in-app message to avoid 404 page.
    console.error('Navigation check failed:', err);
    appendMessage(`Cannot reach "${url}" from this page. Either the file doesn't exist, or network/CORS blocked the check.`, 'bot');
  }
}

async function safeOpen(url) {
  try {
    const resp = await fetch(url, { method: 'HEAD' });
    if (resp.ok) {
      window.open(url, '_blank');
    } else {
      appendMessage(`Sorry — "${url}" was not found on the server (HTTP ${resp.status}).`, 'bot');
    }
  } catch (err) {
    console.error('Open-check failed:', err);
    appendMessage(`Cannot open "${url}". The file may be missing or network/CORS blocked the check.`, 'bot');
  }
}

/* ---------- REPLACE NAVIGATION CALLS ---------- */
const sharedHelpEmail = window.APP_CONTEXT?.helpEmail || 'nischaykademane@gmail.com';

/* Replace these previous simple navigations:
   openExploreBtn.addEventListener('click', ()=>{ window.location.href = '/overview'; });
   openMentorBtn.addEventListener('click', ()=>{ window.location.href = '/mentor'; });
   gad9ResultBtn.addEventListener('click', () => { window.location.href = '/gad9'; });
   handleHelpAction('terms') previously used window.open('/terms', '_blank'); */

if(openExploreBtn){
  openExploreBtn.removeEventListener?.('click', ()=>{}); // defensive: remove earlier handler if present
  openExploreBtn.addEventListener('click', (e) => {
    e.preventDefault();
    safeNavigate('/overview');
  });
}

if(openMentorBtn){
  openMentorBtn.removeEventListener?.('click', ()=>{});
  openMentorBtn.addEventListener('click', (e) => {
    e.preventDefault();
    safeNavigate('/mentor');
  });
}

if(gad9ResultBtn){
  gad9ResultBtn.removeEventListener?.('click', ()=>{});
  gad9ResultBtn.addEventListener('click', (e) => {
    e.preventDefault();
    safeNavigate('/gad9');
  });
}

/* Update help action for terms to use safeOpen */
function handleHelpAction(action){
  switch(action){
    case 'help-center':
      window.location.href = `mailto:${sharedHelpEmail}?subject=I%20need%20support`;
      appendMessage('Opening your email so you can contact our help desk directly.', 'bot');
      break;
    case 'terms':
      // try to open terms file only if present
      safeOpen('/terms');
      appendMessage('Attempted to open terms & policies — if the file is missing you will see a message here instead of a 404.', 'bot');
      break;
    case 'report-bug':
      window.location.href = `mailto:${sharedHelpEmail}?subject=Bug%20report`;
      appendMessage('Tell me what broke in the email draft that just opened—we typically fix priority bugs within a day.', 'bot');
      break;
    default:
      appendMessage('Let me know how else I can help.', 'bot');
  }
}
