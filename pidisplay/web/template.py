def build_dashboard_page() -> str:
    return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>PIDisplay Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050816;
      --panel: rgba(12, 24, 48, 0.92);
      --border: rgba(255, 255, 255, 0.16);
      --text: #f7f9ff;
      --muted: #8fa1c8;
      --accent: #5fd0ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(145deg, var(--bg), #101b35);
      color: var(--text);
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .shell {
      min-height: 100vh;
      padding: 2.2vh 2.2vw;
      display: flex;
      align-items: stretch;
      justify-content: center;
    }
    .grid {
      width: min(100%, 1400px);
      height: min(100%, 1920px);
      display: grid;
      grid-template-columns: 1fr;
      grid-template-rows: auto auto auto;
      gap: 1.5rem;
      flex: 1;
    }
    .header-panel {
      grid-column: 1;
      grid-row: 1;
      min-height: 220px;
      justify-content: center;
      align-items: flex-start;
      padding: 2rem 2.4rem;
    }
    .sensor-panel {
      grid-column: 1;
      grid-row: 3;
    }
    .departures-panel {
      grid-column: 1;
      grid-row: 2;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
      padding: 1.6rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
    }
    .panel h1, .panel h2, .panel h3 {
      margin: 0;
      font-weight: 600;
    }
    .tag {
      color: var(--accent);
      font-size: 0.95rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
    }
    .value {
      font-size: clamp(2rem, 4.8vw, 3.6rem);
      font-weight: 700;
      line-height: 1.1;
      margin-top: 0.6rem;
    }
    .muted {
      color: var(--muted);
      font-size: clamp(0.95rem, 1.7vw, 1.2rem);
      line-height: 1.5;
    }
    .time-box {
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.5rem;
      width: 100%;
    }
    .weather-block {
      min-width: 340px;
      padding: 1rem 1.1rem;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 18px;
      background: rgba(255,255,255,0.04);
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .weather-hours {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0.7rem;
    }
    .weather-hour {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.35rem;
      padding: 0.7rem 0.4rem;
      border-radius: 12px;
      background: rgba(255,255,255,0.05);
      font-size: clamp(1.1rem, 1.9vw, 1.5rem);
    }
    .weather-hour .time {
      color: var(--accent);
      font-weight: 600;
    }
    .clock {
      font-size: clamp(5.2rem, 10vw, 9.6rem);
      font-weight: 700;
      line-height: 1;
    }
    .date {
      font-size: clamp(2.1rem, 3.8vw, 3.1rem);
      color: var(--muted);
    }
    .list {
      display: grid;
      gap: 0.8rem;
      margin-top: 1rem;
    }
    .list div {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.4rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      font-size: clamp(1rem, 1.7vw, 1.2rem);
    }
    .sensor-table {
      display: grid;
      gap: 0.65rem;
      margin-top: 0.2rem;
    }
    .sensor-row {
      display: grid;
      grid-template-columns: 1.4fr 1fr 1fr 1fr;
      gap: 0.8rem;
      align-items: center;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 0.6rem;
      font-size: clamp(1rem, 1.5vw, 1.16rem);
    }
    .sensor-head {
      border-top: none;
      padding-top: 0;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: clamp(0.8rem, 1.1vw, 0.92rem);
      font-weight: 600;
    }
    .transit-table {
      display: grid;
      gap: 0.7rem;
      margin-top: 1rem;
    }
    .transit-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      align-items: center;
      gap: 0.9rem;
      padding-top: 0.4rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      font-size: clamp(1rem, 1.7vw, 1.2rem);
    }
    .transit-head {
      border-top: none;
      padding-top: 0;
      font-size: clamp(0.82rem, 1.2vw, 0.92rem);
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      font-weight: 600;
    }
    .transit-time {
      font-size: clamp(4.8rem, 8.2vw, 5.8rem);
      font-weight: 700;
      text-align: left;
    }
    .transit-time.live {
      color: var(--accent);
    }
    .transit-fallback {
      margin: 0;
    }
    @media (max-width: 900px) {
      .shell { padding: 1rem; }
      .header-panel {
        min-height: auto;
      }
      .transit-row {
        gap: 0.6rem;
      }
    }
  </style>
</head>
<body>
  <div class=\"shell\">
    <div class=\"grid\">
      <section class=\"panel header-panel\">
        <div class=\"header-content\">
          <div class=\"time-box\">
            <div class=\"tag\">Live clock</div>
            <div id=\"clock\" class=\"clock\">--:--:--</div>
            <div id=\"date\" class=\"date\">--</div>
          </div>
          <div class=\"weather-block\">
            <div class=\"tag\">Helsinki forecast</div>
            <div id=\"weather-forecast\" class=\"weather-hours\">
              <p class=\"muted\">Loading…</p>
            </div>
          </div>
        </div>
      </section>
      <section class=\"panel departures-panel\">
        <div>
          <div class=\"tag\">Next departures</div>
          <h3>Merisotilaantori</h3>
        </div>
        <div class=\"transit-table\">
          <div class=\"transit-row transit-head\">
            <span>Leave home at</span>
            <span>Tram departs at</span>
          </div>
          <div id=\"transit-list\" class=\"transit-table-body\">
            <p class=\"muted transit-fallback\">Loading\u2026</p>
          </div>
        </div>
        <p id=\"transit-updated\" class=\"muted\"></p>
      </section>
      <section class=\"panel sensor-panel\">
        <div class=\"sensor-table\">
          <div class=\"sensor-row sensor-head\">
            <span>Sensor</span>
            <span>Temperature</span>
            <span>Humidity</span>
            <span>Pressure</span>
          </div>
          <div id=\"sensor-table-body\"></div>
        </div>
      </section>
    </div>
  </div>
  <script>
    const elements = {
      clock: document.getElementById('clock'),
      date: document.getElementById('date'),
      sensorTableBody: document.getElementById('sensor-table-body'),
      weatherForecast: document.getElementById('weather-forecast')
    };

    function updateClock() {
      const now = new Date();
      elements.clock.textContent = now.toLocaleTimeString('en-GB');
      elements.date.textContent = now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    }

    function renderSensorRows(sensors) {
      if (!elements.sensorTableBody) {
        return;
      }
      const rows = (sensors || []).map((sensor) => {
        const name = sensor.name || '--';
        const temperature = sensor.temperature || '--';
        const humidity = sensor.humidity || '--';
        const pressure = sensor.pressure || '--';
        return `<div class=\"sensor-row\"><span>${name}</span><span>${temperature}</span><span>${humidity}</span><span>${pressure}</span></div>`;
      }).join('');
      elements.sensorTableBody.innerHTML = rows;
    }

    function renderWeather(hours) {
      if (!elements.weatherForecast) {
        return;
      }
      if (!hours || !hours.length) {
        elements.weatherForecast.innerHTML = '<p class="muted">Unavailable</p>';
        return;
      }
      const html = hours.map((hour) => `
        <div class="weather-hour">
          <span class="time">${hour.time || '--'}</span>
          <span>${hour.temperature || '--'}</span>
          <span>${hour.chance_of_rain || '--'}</span>
        </div>
      `).join('');
      elements.weatherForecast.innerHTML = html;
    }

    function updateDashboard(data) {
      renderSensorRows(data.sensors || []);
      renderWeather(data.weather && data.weather.hours ? data.weather.hours : []);
    }

    async function refreshData() {
      try {
        const response = await fetch('/api/data');
        const data = await response.json();
        updateDashboard(data);
      } catch (error) {
        console.error(error);
      }
    }

    updateClock();
    refreshData();
    setInterval(updateClock, 1000);
    setInterval(refreshData, 3000);

    function leaveHomeAt(departureTime, offsetMinutes = 4) {
      const match = /^(\\d{1,2}):(\\d{2})$/.exec(String(departureTime || ''));
      if (!match) {
        return '--';
      }
      const hours = Number(match[1]);
      const minutes = Number(match[2]);
      if (Number.isNaN(hours) || Number.isNaN(minutes) || hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
        return '--';
      }
      const minutesPerDay = 24 * 60;
      const totalMinutes = (((hours * 60) + minutes - offsetMinutes) % minutesPerDay + minutesPerDay) % minutesPerDay;
      const leaveHours = Math.floor(totalMinutes / 60);
      const leaveMinutes = totalMinutes % 60;
      return `${String(leaveHours).padStart(2, '0')}:${String(leaveMinutes).padStart(2, '0')}`;
    }

    async function fetchTransit() {
      try {
        const resp = await fetch('/api/transit');
        const data = await resp.json();
        const departures = data.departures;
        const list = document.getElementById('transit-list');
        if (data.status) {
          list.innerHTML = `<p class=\"muted transit-fallback\">${data.status}</p>`;
        } else if (!departures.length) {
          list.innerHTML = '<p class=\"muted transit-fallback\">No departures available.</p>';
        } else {
          list.innerHTML = departures.map((a) => {
            const live = a.is_realtime;
            const departureTime = live ? a.realtime : a.scheduled;
            const leaveTime = leaveHomeAt(departureTime, 4);
            const liveClass = live ? ' live' : '';
            return `<div class=\"transit-row\"><strong class=\"transit-time\">${leaveTime}</strong><strong class=\"transit-time${liveClass}\">${departureTime}</strong></div>`;
          }).join('');
        }
        document.getElementById('transit-updated').textContent =
          'Updated ' + new Date().toLocaleTimeString('en-GB');
      } catch (e) {
        console.error(e);
      }
    }

    fetchTransit();
    setInterval(fetchTransit, 300000);
  </script>
</body>
</html>
    """
