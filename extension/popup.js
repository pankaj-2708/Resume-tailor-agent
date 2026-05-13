document.addEventListener('DOMContentLoaded', () => {
  const tailorBtn = document.getElementById('tailorBtn');
  const jdInput = document.getElementById('jd');
  const resumeInput = document.getElementById('resume');
  const statusDiv = document.getElementById('status');

  // Replace this with your actual backend URL later
  const BACKEND_URL = 'http://localhost:8000/tailor_resume';

  tailorBtn.addEventListener('click', async () => {
    const jd = jdInput.value.trim();
    const resume = resumeInput.value.trim();

    if (!jd || !resume) {
      showStatus('Please provide both Job Description and Resume content.', 'error');
      return;
    }

    // Update UI to show loading state
    tailorBtn.disabled = true;
    tailorBtn.textContent = 'Tailoring...';
    showStatus('Sending request to backend...', 'success'); // Initial success to show it's working

    try {
      const response = await fetch(BACKEND_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_description: jd,
          resume_path: resume
        }),
      });

      const data = await response.json();

      if (response.ok) {
        showStatus(data, 'success');
      } else {
        showStatus(data, 'error');
      }
    } catch (error) {
      console.error('Fetch error:', error);
      showStatus({ message: `An error occurred while connecting to the backend: ${error.message}` }, 'error');
    } finally {
      tailorBtn.disabled = false;
      tailorBtn.textContent = 'Tailor Resume';
    }
  });

  function showStatus(data, type) {
    statusDiv.className = `status-container ${type}`;
    statusDiv.classList.remove('hidden');

    if (typeof data === 'string') {
      statusDiv.textContent = data;
      return;
    }

    let html = '';

    if (type === 'success') {
      const message = data.message || 'Resume tailored successfully!';
      html = `<div>${message}</div>`;

      if (data.org_resume_score !== undefined && data.updated_resume_score !== undefined) {
        const diff = data.updated_resume_score - data.org_resume_score;
        const diffText = diff >= 0 ? `+${diff}` : `${diff}`;
        html += `
          <div class="score-card">
            <div class="score-item">
              <span class="score-label">Original</span>
              <span class="score-value">${data.org_resume_score}</span>
            </div>
            <div class="score-diff">${diffText}</div>
            <div class="score-item">
              <span class="score-label">Updated</span>
              <span class="score-value">${data.updated_resume_score}</span>
            </div>
          </div>
        `;
      }
    } else if (type === 'error') {
      const message = data.message || data.error || 'An unexpected error occurred';
      html = `<div>${message}</div>`;

      if (data.error) {
        html += `<div class="error-detail"><strong>Details:</strong><br>${data.error}</div>`;
      }
      if (data.last_completed_node) {
        html += `<div class="error-detail"><span class="node-badge">Node: ${data.last_completed_node}</span></div>`;
      }
    }

    statusDiv.innerHTML = html;
  }
});
