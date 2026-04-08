document.querySelectorAll('.table-radio').forEach(radio => {
    radio.addEventListener('change', function() {
        const tableNum = this.value;
        const capacity = this.getAttribute('data-capacity'); // Dito natin kukunin yung 2 o 4
        
        // I-update ang hidden inputs para sa Form
        document.getElementById('selected_table_input').value = tableNum;
        document.getElementById('pax_input').value = capacity;
        
        // I-update ang Button style
        const btn = document.getElementById('submit_btn');
        btn.disabled = false;
        btn.innerHTML = `Reserve Table ${tableNum} (${capacity} Pax)`;
        btn.classList.remove('bg-gray-800', 'text-gray-500');
        btn.classList.add('bg-yellow-500', 'text-black', 'hover:scale-105', 'shadow-xl');
    });
});