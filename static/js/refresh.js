// AUTO-REFRESH LOGIC
// Magre-refresh ang page tuwing 30 seconds para laging updated ang Table Map
let refreshInterval = setInterval(function() {
    // I-check muna natin kung hindi ba nagta-type si user sa search bar
    // para hindi mawala ang focus 
    const searchInput = document.getElementById('masterGuestSearch') || document.getElementById('sidebar-search');
    
    if (searchInput && searchInput.value === "") {
        console.log("System Auto-Syncing...");
        window.location.reload();
    }
}, 30000); //  = 30 seconds

// Para ma-pause ang refresh kapag may ginagawa si staff
window.addEventListener('mousemove', function() {
   
});