document.addEventListener('keydown', function (e) {
    if (e.target.id === 'chat-input') {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); // Prevent default new line behavior
            var sendBtn = document.getElementById('chat-send-btn');
            if (sendBtn) {
                sendBtn.click();
            }
        }
    }
});
