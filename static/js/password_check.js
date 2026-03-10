function togglePassword() {
    const passInput = document.getElementById('staff_password');
    const eyeIcon = document.getElementById('eye_icon');
    if (passInput.type === 'password') {
        passInput.type = 'text';
        eyeIcon.classList.add('text-red-500');
    } else {
        passInput.type = 'password';
        eyeIcon.classList.remove('text-red-500');
    }
}

document.getElementById('staff_password').addEventListener('input', function() {
    const pass = this.value;
    const bar = document.getElementById('strength_bar');
    const text = document.getElementById('strength_text');
    
    // RegEx Checks
    const hasNum = /\d/.test(pass);
    const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(pass);
    const hasUpper = /[A-Z]/.test(pass);
    const hasLower = /[a-z]/.test(pass);
    const isLong = pass.length >= 8;

    // Update Checklist Colors (Green if pass, Gray if fail)
    document.getElementById('req_char').style.color = isLong ? '#22c55e' : '#4b5563';
    document.getElementById('req_upper').style.color = hasUpper ? '#22c55e' : '#4b5563';
    document.getElementById('req_lower').style.color = hasLower ? '#22c55e' : '#4b5563';
    document.getElementById('req_num').style.color = hasNum ? '#22c55e' : '#4b5563';
    document.getElementById('req_special').style.color = hasSpecial ? '#22c55e' : '#4b5563';

    // Strength Points (Max 5)
    let strength = 0;
    if (isLong) strength++;
    if (hasUpper) strength++;
    if (hasLower) strength++;
    if (hasNum) strength++;
    if (hasSpecial) strength++;

    // UI Feedback Base sa Points
    if (pass.length === 0) {
        bar.style.width = '0%';
        text.innerText = 'NONE';
        text.style.color = '#4b5563';
    } else if (strength <= 2) {
        bar.style.width = '33%';
        bar.style.backgroundColor = '#ef4444'; // Red
        text.innerText = 'WEAK';
        text.style.color = '#ef4444';
    } else if (strength <= 4) {
        bar.style.width = '66%';
        bar.style.backgroundColor = '#f59e0b'; // Amber
        text.innerText = 'MEDIUM';
        text.style.color = '#f59e0b';
    } else if (strength === 5) {
        bar.style.width = '100%';
        bar.style.backgroundColor = '#22c55e'; // Green
        text.innerText = 'STRONG';
        text.style.color = '#22c55e';
    }
});