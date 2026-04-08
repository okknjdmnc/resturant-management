// MODAL FUNCTIONS
const modal = document.getElementById('confirmModal');
const paymentForm = document.getElementById('paymentForm');

// Palitan ang behavior ng form submit
paymentForm.addEventListener('submit', function(e) {
    e.preventDefault(); // Huwag muna i-submit agad
    openModal();
});

function openModal() {
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden'; // Lock scrolling
}

function closeModal() {
    modal.classList.add('hidden');
    document.body.style.overflow = 'auto'; // Unlock scrolling
}

function submitFinalPayment() {
    // Ipakita ang loading state sa button (Optional)
    event.target.innerText = "Processing...";
    event.target.disabled = true;
    
    // Ngayon natin i-submit ang form
    paymentForm.submit();
}

// Close modal if clicked outside
window.onclick = function(event) {
    if (event.target == modal.querySelector('.absolute.inset-0')) {
        closeModal();
    }
}