if (window.history.replaceState) {
    window.history.replaceState(null, null, window.location.href);
}

window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
        window.location.reload();
    }
})