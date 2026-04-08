function calculateChange() {
        // Kunin ang total bill mula sa hidden input
        const total = parseFloat(document.getElementById('grand_total_val').value);
        // Kunin ang binayad ng customer
        const received = parseFloat(document.getElementById('cash_received').value) || 0;
        
        const change = received - total;
        const display = document.getElementById('change_display');
        
        if (change >= 0) {
            // I-format ang number na may commas (₱ 1,000.00)
            display.innerText = '₱ ' + change.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            display.classList.remove('text-red-400');
            display.classList.add('text-emerald-400');
        } else {
            // Kapag kulang ang pera, gawing 0.00 at kulay pula
            display.innerText = '₱ 0.00';
            display.classList.remove('text-emerald-400');
            display.classList.add('text-red-400');
        }
    }

    function toggleCashInput(isCash) {
        const calc = document.getElementById('cash_calculator');
        const input = document.getElementById('cash_received');
        const display = document.getElementById('change_display');

        if(isCash) {
            // Kapag Cash, gawing visible at clickable
            calc.style.opacity = '1';
            calc.style.pointerEvents = 'auto';
            input.focus();
        } else {
            // Kapag GCash, i-dim at i-reset ang values
            calc.style.opacity = '0.3';
            calc.style.pointerEvents = 'none';
            input.value = '';
            display.innerText = '₱ 0.00';
        }
    }

    // Siguraduhin na naka-focus sa input pag-load kung cash ang default
    window.onload = () => {
        if(document.querySelector('input[name="payment_method"]:checked').value === 'cash') {
            document.getElementById('cash_received').focus();
        }
    }