document.addEventListener('DOMContentLoaded', function() {
    const paxInput = document.getElementById('pax_input');
    const errorMsg = document.getElementById('pax-error-msg');
    const submitBtn = document.getElementById('submit-btn');
    
    // Kunin ang package ID mula sa hidden input
    const packageId = document.querySelector('input[name="event_package"]').value;

    paxInput.addEventListener('input', function() {
        const val = parseInt(this.value);
        let isValid = true;
        let message = "";

        // Rules base sa package
        if (packageId === 'party_prime') {
            if (val < 15 || val > 25) {
                isValid = false;
                message = "❌ Party Prime is strictly for 15-25 persons only.";
            }
        } else if (packageId === 'grand_feast') {
            if (val < 30 || val > 50) {
                isValid = false;
                message = "❌ Grand Feast is strictly for 30-50 persons only.";
            }
        } else {
            if (val < 15) {
                isValid = false;
                message = "❌ Minimum 15 pax required for events.";
            }
        }

        // Real-time Visual Feedback
        if (!isValid && this.value !== "") {
            // Pakita ang error
            errorMsg.textContent = message;
            errorMsg.classList.remove('hidden');
            
            // Gawing pula ang border
            this.classList.add('border-red-500/50', 'bg-red-500/5');
            this.classList.remove('border-white/10', 'bg-white/[0.03]');
            
            // I-disable ang submit button
            submitBtn.disabled = true;
            submitBtn.classList.add('opacity-30', 'cursor-not-allowed');
            submitBtn.textContent = "Invalid Pax Count";
        } else {
            // Itago ang error
            errorMsg.classList.add('hidden');
            
            // Balik sa normal na style
            this.classList.remove('border-red-500/50', 'bg-red-500/5');
            this.classList.add('border-white/10', 'bg-white/[0.03]');
            
            // Enable submit button
            submitBtn.disabled = false;
            submitBtn.classList.remove('opacity-30', 'cursor-not-allowed');
            submitBtn.textContent = "Send Inquiry";
        }
    });
});