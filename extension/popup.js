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
        showStatus(data.res || data.message || 'Resume tailored successfully!', 'success');
      } else {
        let errorMessage = data.error || `Error occurred: ${response.statusText}`;
        if (data.last_completed_node) {
          errorMessage += `\nFailed at node: ${data.last_completed_node}`;
        }
        showStatus(errorMessage, 'error');
      }
    } catch (error) {
      console.error('Fetch error:', error);
      showStatus(`An error occurred while connecting to the backend: ${error.message}`, 'error');
    } finally {
      tailorBtn.disabled = false;
      tailorBtn.textContent = 'Tailor Resume';
    }
  });

  function showStatus(message, type) {
    statusDiv.textContent = message;
    statusDiv.className = `status-message ${type}`;
    statusDiv.classList.remove('hidden');
  }
});
