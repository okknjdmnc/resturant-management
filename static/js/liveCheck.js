function updateClock() {
            const now = new Date();
            document.getElementById('live-clock').innerText = now.toLocaleString('en-US', { 
                hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true,
                weekday: 'short', month: 'short', day: 'numeric'
            });
        }
        setInterval(updateClock, 1000);
        updateClock();