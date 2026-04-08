document.addEventListener('DOMContentLoaded', function() {
    const calendarInput = document.getElementById('event_calendar');
    const warning = document.getElementById('date-warning');

    // 1. Kunin ang booked dates mula sa database via API
    fetch('/api/booked-dates')
        .then(response => response.json())
        .then(bookedDates => {
            
            // 2. I-initialize ang Flatpickr
            flatpickr("#event_calendar", {
                minDate: "today",      // Bawal mag-book ng past dates
                dateFormat: "Y-m-d",   // Format na pasok sa MySQL DATETIME
                disable: bookedDates,  // Dito papasok ang array: ["2026-03-25", "2026-03-28"]
                
                locale: {
                    firstDayOfWeek: 1
                },
                
                onChange: function(selectedDates, dateStr) {
                    // Double check kung sakaling na-click (though disabled na dapat)
                    if (bookedDates.includes(dateStr)) {
                        warning.classList.remove('hidden');
                        document.getElementById('submit-btn').disabled = true;
                        document.getElementById('submit-btn').style.opacity = "0.5";
                    } else {
                        warning.classList.add('hidden');
                        document.getElementById('submit-btn').disabled = false;
                        document.getElementById('submit-btn').style.opacity = "1";
                    }
                }
            });
        })
        .catch(err => console.error("Error fetching booked dates:", err));
});