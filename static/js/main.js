// document.addEventListener('DOMContentLoaded', () => {
//     const socket = io(); // Connect to Socket.IO server

//     const uploadForm = document.getElementById('uploadForm');
//     const targetImageInput = document.getElementById('targetImage');
//     const submitTargetBtn = document.getElementById('submitTargetBtn');
//     const uploadStatusDiv = document.getElementById('uploadStatus');

//     const verifyBtn = document.getElementById('verifyBtn');
//     const videoElement = document.getElementById('videoElement');
//     const verificationStatusDiv = document.getElementById('verificationStatus');
//     const finalResultDiv = document.getElementById('finalResult');

//     let stream;
//     let videoInterval;
//     const VERIFICATION_TIMEOUT_MS = 10000; // 10 seconds
//     let verificationTimer;

//     function displayMessage(element, message, type) {
//         element.textContent = message;
//         element.className = 'status-message'; // Reset classes
//         if (type === 'success') {
//             element.classList.add('status-success');
//         } else if (type === 'error') {
//             element.classList.add('status-error');
//         } else {
//             element.classList.add('status-info');
//         }
//         element.style.display = 'block';
//     }

//     uploadForm.addEventListener('submit', async (event) => {
//         event.preventDefault();
//         const formData = new FormData();
//         formData.append('target_image', targetImageInput.files[0]);

//         submitTargetBtn.disabled = true;
//         displayMessage(uploadStatusDiv, 'Uploading and processing target image...', 'info');

//         try {
//             const response = await fetch('/upload_target', {
//                 method: 'POST',
//                 body: formData,
//             });
//             const result = await response.json();

//             if (response.ok && result.status === 'success') {
//                 displayMessage(uploadStatusDiv, result.message, 'success');
//                 verifyBtn.disabled = false;
//                 console.log("Target image processed successfully.");
//             } else {
//                 displayMessage(uploadStatusDiv, `Error: ${result.message}`, 'error');
//                 console.error("Target image upload/processing failed:", result.message);
//             }
//         } catch (error) {
//             displayMessage(uploadStatusDiv, `Network or server error: ${error.message}`, 'error');
//             console.error("Error submitting target image:", error);
//         } finally {
//             submitTargetBtn.disabled = false;
//         }
//     });

//     verifyBtn.addEventListener('click', async () => {
//         verifyBtn.disabled = true;
//         displayMessage(verificationStatusDiv, 'Attempting to start camera...', 'info');
//         displayMessage(finalResultDiv, '', 'info'); // Clear previous results
//         finalResultDiv.style.display = 'none';

//         try {
//             stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
//             videoElement.srcObject = stream;
//             videoElement.style.display = 'block'; // Show video element
            
//             console.log("Camera started. Initiating verification with backend.");
//             displayMessage(verificationStatusDiv, 'Camera active. Starting verification...', 'info');
//             socket.emit('start_verify'); // Tell backend to prepare

//             // Start sending frames after a short delay to ensure video is playing
//             setTimeout(() => {
//                 if (stream && stream.active) {
//                      videoInterval = setInterval(sendFrameToServer, 200); // Send frame every 200ms (5 FPS)
//                      console.log("Sending video frames to server...");
//                 }
//             }, 500);

//             // Set a timeout for the verification process on the client side
//             clearTimeout(verificationTimer); // Clear any existing timer
//             verificationTimer = setTimeout(() => {
//                 console.log("Client-side verification timeout (10 seconds).");
//                 stopVerificationProcess('Person detection failed (client timeout).');
//                 socket.emit('stop_verify'); // Inform backend explicitly if client times out
//             }, VERIFICATION_TIMEOUT_MS);

//         } catch (err) {
//             console.error("Error accessing camera:", err);
//             displayMessage(verificationStatusDiv, `Error accessing camera: ${err.message}. Please ensure permissions are granted.`, 'error');
//             verifyBtn.disabled = false;
//         }
//     });

//     function sendFrameToServer() {
//         if (!stream || !stream.active) {
//             console.log("Stream not active, stopping frame sending.");
//             stopVerificationProcess('Camera stream lost.');
//             return;
//         }

//         const canvas = document.createElement('canvas');
//         canvas.width = videoElement.videoWidth;
//         canvas.height = videoElement.videoHeight;
//         const context = canvas.getContext('2d');
//         context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
//         const dataURL = canvas.toDataURL('image/jpeg', 0.8); // Send as JPEG for efficiency
//         socket.emit('video_frame', dataURL);
//     }

//     function stopVerificationProcess(finalMessage, type = 'failed') {
//         console.log("Stopping verification process. Message:", finalMessage);
//         clearInterval(videoInterval);
//         clearTimeout(verificationTimer);

//         if (stream) {
//             stream.getTracks().forEach(track => track.stop());
//             stream = null;
//         }
//         videoElement.srcObject = null;
//         // videoElement.style.display = 'none'; // Keep video element visible if you prefer

//         verifyBtn.disabled = false; // Re-enable verify button
        
//         let messageType = 'error';
//         if (type === 'success') messageType = 'success';
//         else if (type === 'info') messageType = 'info';

//         displayMessage(verificationStatusDiv, 'Verification ended.', 'info');
//         displayMessage(finalResultDiv, finalMessage, messageType);
//         console.log("Final Result:", finalMessage);
//         videoElement.style.display = 'none';

//     }

//     socket.on('verification_status', (data) => {
//         console.log('Verification status from server:', data);
//         displayMessage(verificationStatusDiv, data.message, data.status === 'error' ? 'error' : 'info');
//     });

//     socket.on('verification_result', (data) => {
//         console.log('Verification result from server:', data);
//         if (data.status === 'success') {
//             stopVerificationProcess(data.message, 'success');
//         } else {
//             // If it's a failure from the server, but client timeout hasn't hit,
//             // this will stop it.
//             stopVerificationProcess(data.message, 'failed');
//         }
//     });

//     // Handle potential disconnects
//     socket.on('disconnect', () => {
//         console.log('Disconnected from server.');
//         // displayMessage(verificationStatusDiv, 'Disconnected from server. Please refresh.', 'error');
//         // Optionally try to clean up if verification was in progress
//         if (videoInterval) { // If verification was running
//             stopVerificationProcess('Disconnected from server during verification.');
//         }
//     });
// });





document.addEventListener('DOMContentLoaded', () => {
    const socket = io(); // Connect to Socket.IO server

    // --- Element Selections ---
    const uploadForm = document.getElementById('uploadForm');
    const targetImageInput = document.getElementById('targetImage');
    const submitTargetBtn = document.getElementById('submitTargetBtn');
    const uploadStatusDiv = document.getElementById('uploadStatus');

    const verifyBtn = document.getElementById('verifyBtn');
    const videoElement = document.getElementById('videoElement');
    const verificationStatusDiv = document.getElementById('verificationStatus');
    const finalResultDiv = document.getElementById('finalResult');

    // --- State Variables ---
    let stream;
    let videoInterval;
    const VERIFICATION_TIMEOUT_MS = 10000; // 10 seconds (client-side backup timer)
    let verificationTimer;

    // --- Initial UI State ---
    if (submitTargetBtn) submitTargetBtn.disabled = true; // Disabled until socket connects
    if (verifyBtn) verifyBtn.disabled = true;       // Disabled until target is uploaded

    // --- Utility Functions ---
    function displayMessage(element, message, type) {
        if (!element) return;
        element.textContent = message;
        element.className = 'status-message'; // Reset classes
        if (type === 'success') {
            element.classList.add('status-success');
        } else if (type === 'error') {
            element.classList.add('status-error');
        } else { // 'info' or default
            element.classList.add('status-info');
        }
        element.style.display = 'block';
    }

    // --- Socket.IO Event Handlers ---
    socket.on('connect', () => {
        console.log('Socket.IO connected! Socket ID:', socket.id);
        if (submitTargetBtn) {
            submitTargetBtn.disabled = false; // Enable target upload now
        }
        displayMessage(uploadStatusDiv, 'Connected to server. Ready to upload target image.', 'info');
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from server.');
        displayMessage(uploadStatusDiv, 'Disconnected. Please refresh.', 'error');
        if (submitTargetBtn) submitTargetBtn.disabled = true;
        if (verifyBtn) verifyBtn.disabled = true;
        // Optionally try to clean up if verification was in progress
        if (videoInterval) { // If verification was running
            stopVerificationProcess('Disconnected from server during verification.');
        }
    });

    socket.on('connect_error', (error) => {
        console.error('Socket.IO connection error:', error);
        displayMessage(uploadStatusDiv, 'Connection Error. Please refresh.', 'error');
        if (submitTargetBtn) submitTargetBtn.disabled = true;
        if (verifyBtn) verifyBtn.disabled = true;
    });

    // --- Target Image Upload Logic ---
    if (uploadForm) {
        uploadForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            if (!targetImageInput.files || targetImageInput.files.length === 0) {
                displayMessage(uploadStatusDiv, 'Please select an image file.', 'error');
                return;
            }

            // Ensure socket is connected and has an ID before proceeding
            if (!socket || !socket.connected || !socket.id) {
                displayMessage(uploadStatusDiv, 'Error: Not connected to server. Please wait or refresh.', 'error');
                console.error("Upload attempt while socket not ready:", {
                    connected: socket ? socket.connected : 'N/A',
                    id: socket ? socket.id : 'N/A'
                });
                return;
            }

            const formData = new FormData();
            formData.append('target_image', targetImageInput.files[0]);
            formData.append('socket_id', socket.id); // *** CRITICAL: Add socket_id ***

            submitTargetBtn.disabled = true;
            verifyBtn.disabled = true; // Keep verify disabled during upload
            displayMessage(uploadStatusDiv, 'Uploading and processing target image...', 'info');

            try {
                const response = await fetch('/upload_target', {
                    method: 'POST',
                    body: formData,
                });
                const result = await response.json();

                if (response.ok && result.status === 'success') {
                    displayMessage(uploadStatusDiv, result.message, 'success');
                    verifyBtn.disabled = false; // Enable verification button
                    console.log("Target image processed successfully.");
                } else {
                    displayMessage(uploadStatusDiv, `Error: ${result.message || 'Unknown error during upload.'}`, 'error');
                    console.error("Target image upload/processing failed:", result.message);
                }
            } catch (error) {
                displayMessage(uploadStatusDiv, `Network or server error: ${error.message}`, 'error');
                console.error("Error submitting target image:", error);
            } finally {
                submitTargetBtn.disabled = false; // Re-enable upload button
            }
        });
    }

    // --- Verification Logic ---
    if (verifyBtn) {
        verifyBtn.addEventListener('click', async () => {
            verifyBtn.disabled = true;
            displayMessage(verificationStatusDiv, 'Attempting to start camera...', 'info');
            displayMessage(finalResultDiv, '', 'info'); // Clear previous results
            finalResultDiv.style.display = 'none';

            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                videoElement.srcObject = stream;
                videoElement.style.display = 'block';
                
                console.log("Camera started. Initiating verification with backend.");
                displayMessage(verificationStatusDiv, 'Camera active. Starting verification...', 'info');
                socket.emit('start_verify');

                setTimeout(() => {
                    if (stream && stream.active) {
                        videoInterval = setInterval(sendFrameToServer, 200); // Approx 5 FPS
                        console.log("Sending video frames to server...");
                    }
                }, 500); // Short delay for video to initialize

                clearTimeout(verificationTimer);
                verificationTimer = setTimeout(() => {
                    console.log("Client-side verification timeout.");
                    if (videoInterval) { // Only if verification is still running
                        socket.emit('stop_verify'); // Inform backend
                        stopVerificationProcess('Person detection failed (client timeout).');
                    }
                }, VERIFICATION_TIMEOUT_MS);

            } catch (err) {
                console.error("Error accessing camera:", err);
                displayMessage(verificationStatusDiv, `Error accessing camera: ${err.message}. Check permissions.`, 'error');
                verifyBtn.disabled = false; // Re-enable verify button on camera error
            }
        });
    }

    function sendFrameToServer() {
        if (!stream || !stream.active || !videoElement.videoWidth || !videoElement.videoHeight) {
            console.log("Stream not active or video dimensions not available, stopping frame sending.");
            // Do not call stopVerificationProcess here directly, let server or timeout handle it
            // unless it's a definitive stop condition.
            if (videoInterval) {
                 // Consider if we should inform server or just let timeout handle it
            }
            return;
        }

        const canvas = document.createElement('canvas');
        canvas.width = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;
        const context = canvas.getContext('2d');
        context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
        const dataURL = canvas.toDataURL('image/jpeg', 0.8); // JPEG for efficiency
        socket.emit('video_frame', dataURL);
    }

    function stopVerificationProcess(finalMessage, type = 'failed') { // type can be 'success', 'failed', 'info'
        console.log("Stopping verification process. Message:", finalMessage, "Type:", type);
        clearInterval(videoInterval);
        videoInterval = null; // Clear interval ID
        clearTimeout(verificationTimer);

        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
        if (videoElement) {
            videoElement.srcObject = null;
            videoElement.style.display = 'none';
        }
        
        if (verifyBtn) verifyBtn.disabled = false;
        
        let messageType = 'error'; // Default to error for 'failed'
        if (type === 'success') messageType = 'success';
        else if (type === 'info') messageType = 'info';

        displayMessage(verificationStatusDiv, 'Verification ended.', 'info');
        displayMessage(finalResultDiv, finalMessage, messageType);
        console.log("Final Result Displayed:", finalMessage);
    }

    // --- Socket Listeners for Verification Flow ---
    socket.on('verification_status', (data) => {
        console.log('Verification status from server:', data);
        displayMessage(verificationStatusDiv, data.message, data.status === 'error' ? 'error' : 'info');
    });

    socket.on('verification_result', (data) => {
        console.log('Verification result from server:', data);
        // Only stop if verification is considered active (videoInterval is set)
        // This prevents acting on stale messages if stopVerificationProcess was already called.
        if (videoInterval || verificationTimer) { // Check if a verification process was active
            if (data.status === 'success') {
                stopVerificationProcess(data.message, 'success');
            } else { // 'failed' or other non-success status from server
                stopVerificationProcess(data.message, 'failed');
            }
        } else {
            console.log("Received verification_result but process already stopped:", data);
        }
    });
});