document.addEventListener('DOMContentLoaded', () => {
  const tailorBtn = document.getElementById('tailorBtn');
  const jdInput = document.getElementById('jd');
  const resumeInput = document.getElementById('resume');
  const resumeNameInput = document.getElementById('resumeName');
  const statusDiv = document.getElementById('status');
  const runningJobsDiv = document.getElementById('runningJobs');
  const jobsList = document.getElementById('jobsList');
  const completedJobsDiv = document.getElementById('completedJobs');
  const completedList = document.getElementById('completedList');

  const API_BASE_URL = 'http://localhost:8000';

  function formatElapsed(startTime) {
    if (!startTime) return 'Calculating...';
    try {
      const start = new Date(startTime.replace(' ', 'T'));
      const now = new Date();
      const diff = Math.floor((now - start) / 1000);
      if (isNaN(diff)) return 'Unknown';
      const m = Math.floor(diff / 60);
      const s = diff % 60;
      return `${m}m ${s}s`;
    } catch (e) {
      return 'Error';
    }
  }

  async function fetchRunningJobs() {
    try {
      const response = await fetch(`${API_BASE_URL}/fetch_running_jobs/`);
      const data = await response.json();

      if (response.ok) {
        const jobs = data.running_jobs || [];
        if (jobs.length > 0) {
          runningJobsDiv.classList.remove('hidden');

          const jobsWithTime = await Promise.all(jobs.map(async (job) => {
            try {
              const statusRes = await fetch(`${API_BASE_URL}/job_status/${job.id}`);
              const statusData = await statusRes.json();
              return { ...job, time_created: statusData.time_created };
            } catch (e) {
              return { ...job, time_created: null };
            }
          }));

          jobsList.innerHTML = jobsWithTime.map(job => `
            <li data-id="${job.id}" data-start="${job.time_created || ''}" title="${job.id}">
              ${job.name}
              <span class="job-timer" style="float:right; font-size: 10px; color: #64748b;">
                ${formatElapsed(job.time_created)}
              </span>
            </li>
          `).join('');
        } else {
          runningJobsDiv.classList.add('hidden');
        }
      }
    } catch (error) {
      console.error('Error fetching running jobs:', error);
    }
  }

  async function fetchCompletedJobs() {
    try {
      const response = await fetch(`${API_BASE_URL}/fetch_completed_jobs/`);
      const data = await response.json();

      if (response.ok) {
        const jobs = data.last_10_jobs || [];
        if (jobs.length > 0) {
          completedJobsDiv.classList.remove('hidden');
          completedList.innerHTML = jobs.map(job => `<li>${job.new_resume_name} <span class="completed-date">${job.time_created}</span></li>`).join('');
        } else {
          completedJobsDiv.classList.add('hidden');
        }
      }
    } catch (error) {
      console.error('Error fetching completed jobs:', error);
    }
  }

  async function pollJobStatus(jobId) {
    console.log(`Waiting 60s before polling job ${jobId}...`);

    await new Promise(resolve => setTimeout(resolve, 60000));

    console.log(`Starting polling for job ${jobId}...`);
    const intervalId = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/job_status/${jobId}`);
        const data = await response.json();

        if (response.ok) {
          if (data.status === 'running') {
             // We can now use the time_created from the API if we update the backend to return it
             console.log(`Job ${jobId} is still running. Started at: ${data.time_created}`);
          } else {
            clearInterval(intervalId);
            alert(`Job ${jobId} Completed!\n\nResume Name: ${data.new_resume_name}\nResponse: ${JSON.stringify(data.response, null, 2)}`);
            fetchRunningJobs();
            fetchCompletedJobs();
          }
        }
      } catch (error) {
        console.error(`Error polling job ${jobId}:`, error);
      }
    }, 10000);
  }

  fetchRunningJobs();
  fetchCompletedJobs();

  setInterval(() => {
    document.querySelectorAll('.job-timer').forEach(span => {
      const li = span.closest('li');
      if (li) {
        const startTime = li.getAttribute('data-start');
        span.textContent = formatElapsed(startTime);
      }
    });
  }, 1000);

  tailorBtn.addEventListener('click', async () => {
    const jd = jdInput.value.trim();
    const resume = resumeInput.value.trim();
    const resumeName = resumeNameInput.value.trim() || 'resume';

    if (!jd || !resume) {
      showStatus('Please provide both Job Description and Resume content.', 'error');
      return;
    }

    tailorBtn.disabled = true;
    tailorBtn.textContent = 'Tailoring...';
    showStatus('Sending request to backend...', 'success');

    try {
      const response = await fetch(`${API_BASE_URL}/create_job`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_description: jd,
          resume_path: resume,
          new_resume_name: resumeName
        }),
      });

      const data = await response.json();

      if (response.ok) {
        showStatus(`Job created successfully! ID: ${data.job_id}`, 'success');
        fetchRunningJobs();
        pollJobStatus(data.job_id);
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
