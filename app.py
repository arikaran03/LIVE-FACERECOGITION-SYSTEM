import os
import cv2
import face_recognition
from deepface import DeepFace
import numpy as np
import base64
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import time
import threading # Re-added
import collections # Re-added

# Initialize Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_should_be_changed!' # Change this!
app.config['UPLOAD_FOLDER'] = 'uploads'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- Session-specific storage ---
# Stores { sid: {"encoding": encoding_array, "filepath": path_to_image, "name": name} }
session_target_encodings = {}
# Stores { sid: {"in_progress": bool, "start_time": float, "found_live": bool} }
session_verification_state = {}

VERIFICATION_DURATION = 10  # seconds
KNOWN_FACE_NAME_DEFAULT = "Target Person"

# --- Global state for managing uploaded files for TTL cleanup ---
IMAGE_TTL_SECONDS = 120  # 2 minutes for each image
CLEANUP_CHECK_INTERVAL_SECONDS = 30 # How often the worker checks for expired files
uploaded_file_registry = collections.deque()  # Stores (filepath, upload_timestamp)
uploaded_files_lock = threading.Lock()  # Lock for uploaded_file_registry
ttl_cleanup_worker_thread = None # To hold the background thread

def background_ttl_cleanup_worker():
    """
    Worker thread that periodically checks for and deletes expired image files
    based on their individual TTL.
    """
    global uploaded_file_registry # Allow modification of global
    print(f"Background TTL cleanup worker started. Image TTL: {IMAGE_TTL_SECONDS}s, Check Interval: {CLEANUP_CHECK_INTERVAL_SECONDS}s.")
    
    while True:
        time.sleep(CLEANUP_CHECK_INTERVAL_SECONDS) # Wait for the defined interval
        now = time.time()
        
        files_to_delete_from_disk = [] # Collect filepaths to delete outside the lock
        
        with uploaded_files_lock: # Acquire lock to safely access/modify the registry
            # Build a new deque with files that haven't expired yet
            non_expired_files = collections.deque()
            
            # Process all items currently in the registry
            # Iterating by popping ensures each item is checked once and removed or re-added
            while uploaded_file_registry: 
                filepath, upload_timestamp = uploaded_file_registry.popleft() # Check oldest first
                
                if (now - upload_timestamp) > IMAGE_TTL_SECONDS:
                    # File has expired
                    print(f"Background TTL cleanup: File {filepath} TTL expired (uploaded at {upload_timestamp}, now {now}). Scheduled for deletion.")
                    files_to_delete_from_disk.append(filepath)
                else:
                    # File has not expired, add it to the temporary deque to be kept
                    non_expired_files.append((filepath, upload_timestamp))
            
            # Replace the old registry with the one containing only non-expired files
            uploaded_file_registry = non_expired_files
            # print(f"Background TTL cleanup: Registry updated. Current size: {len(uploaded_file_registry)}")

        # Delete expired files from disk (outside the lock to avoid holding lock during I/O)
        if files_to_delete_from_disk:
            print(f"Background TTL cleanup: Attempting to delete {len(files_to_delete_from_disk)} expired files from disk.")
            for f_path in files_to_delete_from_disk:
                try:
                    if os.path.exists(f_path):
                        os.remove(f_path)
                        print(f"Background TTL cleanup: Deleted expired image {f_path} from disk.")
                    else:
                        # This might happen if the file was deleted by session disconnect just before TTL cleanup
                        print(f"Background TTL cleanup: Expired image {f_path} already deleted or not found on disk.")
                except Exception as e:
                    print(f"Background TTL cleanup: Error deleting expired image {f_path} from disk: {e}")
        # else:
            # print(f"Background TTL cleanup: No files expired in this cycle.")


def image_to_base64(image_path): # Not used in server, but kept if client might need it
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

@app.route('/')
def index():
    # This will serve your main HTML page.
    # Ensure 'index.html' is in a 'templates' folder in the same directory as your app.py
    return render_template('index.html')

@app.route('/upload_target', methods=['POST'])
def upload_target():
    global uploaded_file_registry # To add new files to the registry
    if 'target_image' not in request.files:
        return jsonify({"status": "error", "message": "No image file provided."}), 400
    
    file = request.files['target_image']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file."}), 400

    socket_id = request.form.get('socket_id')
    if not socket_id:
        return jsonify({"status": "error", "message": "Socket ID is required for target upload."}), 400

    filepath = None
    if file:
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        # Create a unique filename including socket_id and timestamp
        filename = f"target_image_{socket_id}_{int(time.time())}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        old_filepath_removed_for_session = None # To track if an old file was removed from registry
        # Clean up any old image for THIS socket_id first from disk
        if socket_id in session_target_encodings and \
           "filepath" in session_target_encodings[socket_id] and \
           session_target_encodings[socket_id]["filepath"] is not None and \
           os.path.exists(session_target_encodings[socket_id]["filepath"]):
            
            old_filepath_for_sid = session_target_encodings[socket_id]["filepath"]
            try:
                os.remove(old_filepath_for_sid)
                print(f"Removed old target image {old_filepath_for_sid} for SID {socket_id} before new upload.")
                old_filepath_removed_for_session = old_filepath_for_sid # Mark for removal from registry too
            except Exception as e:
                print(f"Error removing old target image for SID {socket_id}: {e}")
        
        file.save(filepath) # Save the new file

        try:
            target_image_data = face_recognition.load_image_file(filepath)
            encodings = face_recognition.face_encodings(target_image_data)
            
            if not encodings:
                if os.path.exists(filepath): os.remove(filepath) # Clean up the newly saved file if no face
                return jsonify({
                    "status": "error", 
                    "message": "No face found in the uploaded image. Please ensure the image contains a clear, single face."
                }), 400
            
            if len(encodings) > 1:
                if os.path.exists(filepath): os.remove(filepath) # Clean up if multiple faces
                return jsonify({
                    "status": "error",
                    "message": f"Multiple faces detected ({len(encodings)} found). Please upload an image with only one person."
                }), 400

            # Store the new encoding and filepath for the session
            session_target_encodings[socket_id] = {
                "encoding": encodings[0],
                "filepath": filepath,
                "name": KNOWN_FACE_NAME_DEFAULT
            }
            
            # Manage the global TTL registry
            with uploaded_files_lock:
                # If an old file for this session was replaced and deleted from disk,
                # remove its old entry from the TTL registry as well.
                if old_filepath_removed_for_session:
                    temp_deque = collections.deque()
                    while uploaded_file_registry: # Iterate through current registry
                        fp_reg, ts_reg = uploaded_file_registry.popleft()
                        if fp_reg != old_filepath_removed_for_session: # Keep if not the one deleted
                            temp_deque.append((fp_reg, ts_reg))
                    uploaded_file_registry = temp_deque # Assign the filtered deque back
                    print(f"Removed {old_filepath_removed_for_session} from TTL registry (replaced by new upload for same SID).")

                # Add new file to TTL registry
                uploaded_file_registry.append((filepath, time.time()))
                print(f"Added {filepath} to TTL registry. Current count in registry: {len(uploaded_file_registry)}")

            print(f"Target face uploaded successfully for SID: {socket_id}. File: {filepath}")
            return jsonify({"status": "success", "message": "Target face uploaded successfully."})
        
        except Exception as e:
            print(f"Error processing target image for SID {socket_id}: {e}")
            if filepath and os.path.exists(filepath): # Clean up the partially processed file on error
                os.remove(filepath)
            # Also remove from registry if it was added just before error
            with uploaded_files_lock:
                # Check if the problematic filepath was the last one added and remove it
                if uploaded_file_registry and uploaded_file_registry[-1][0] == filepath: 
                    uploaded_file_registry.pop()
                    print(f"Removed {filepath} from TTL registry due to processing error.")
            return jsonify({"status": "error", "message": f"Could not process target image. Error: {str(e)}"}), 500
    
    return jsonify({"status": "error", "message": "File could not be processed."}), 400

@socketio.on('start_verify')
def handle_start_verify():
    sid = request.sid
    target_data = session_target_encodings.get(sid)

    # Check if target data exists and its associated file path is still valid
    if not target_data or target_data.get("encoding") is None or target_data.get("filepath") is None:
        emit('verification_result', {'status': 'error', 'message': 'Target image not set. Please upload target image first.'}, room=sid)
        return
    
    # Check if the file actually exists on disk, as TTL might have deleted it
    if not os.path.exists(target_data.get("filepath")):
        emit('verification_result', {'status': 'error', 'message': 'Target image has expired or been removed. Please upload again.'}, room=sid)
        # Clean up stale session entry if file is missing
        if sid in session_target_encodings:
            del session_target_encodings[sid]
        return

    print(f"Verification process started for SID: {sid}.")
    session_verification_state[sid] = {
        'in_progress': True,
        'start_time': time.time(),
        'found_live': False
    }
    emit('verification_status', {'status': 'started', 'message': 'Verification process initiated. Receiving frames...'}, room=sid)


@socketio.on('video_frame')
def handle_video_frame(data_url):
    sid = request.sid
    current_session_state = session_verification_state.get(sid)
    target_session_data = session_target_encodings.get(sid)

    if not current_session_state or not current_session_state.get('in_progress'):
        return # Verification not active for this session

    # It's possible the target image expired between 'start_verify' and receiving frames
    if not target_session_data or target_session_data.get("encoding") is None or \
       not os.path.exists(target_session_data.get("filepath","")): # Check file existence again
        emit('verification_result', {'status': 'error', 'message': 'Target image data missing or expired. Please upload again.'}, room=sid)
        if current_session_state: current_session_state['in_progress'] = False
        # Clean up stale session entry if file is missing
        if sid in session_target_encodings and (not target_session_data or not os.path.exists(target_session_data.get("filepath",""))):
            del session_target_encodings[sid]
        return

    known_face_encoding_for_session = target_session_data["encoding"]

    if time.time() - current_session_state['start_time'] > VERIFICATION_DURATION:
        if not current_session_state.get('found_live', False): # Only send timeout if not already found
            print(f"Verification timed out for SID: {sid}.")
            emit('verification_result', {'status': 'failed', 'message': 'Face mismatch or timeout.'}, room=sid)
        current_session_state['in_progress'] = False # Stop processing further frames
        return

    try:
        # Ensure data_url is a string and contains the expected prefix
        if not isinstance(data_url, str) or not data_url.startswith('data:image/jpeg;base64,'):
            return

        header, encoded = data_url.split(",", 1)
        image_data = base64.b64decode(encoded)
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None: return

        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5) 
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_small_frame) 
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            matches = face_recognition.compare_faces([known_face_encoding_for_session], face_encoding, tolerance=0.5)
            name = "Unknown" 
            if True in matches:
                name = target_session_data.get("name", KNOWN_FACE_NAME_DEFAULT)
                
                top_orig, right_orig, bottom_orig, left_orig = top * 2, right * 2, bottom * 2, left * 2
                padding = 20 
                h, w, _ = frame.shape
                top_orig, left_orig = max(0, top_orig - padding), max(0, left_orig - padding)
                bottom_orig, right_orig = min(h, bottom_orig + padding), min(w, right_orig + padding)
                face_img_for_liveness = frame[top_orig:bottom_orig, left_orig:right_orig]

                if face_img_for_liveness.size == 0: continue
                
                try:
                    liveness_results_list = DeepFace.extract_faces(
                        img_path=face_img_for_liveness, detector_backend='opencv', 
                        align=False, enforce_detection=False, anti_spoofing=True
                    )
                    if liveness_results_list: # Check if list is not empty
                        liveness_result = liveness_results_list[0] 
                        if liveness_result.get("is_real", False): 
                            print(f"Verification successful: Live person detected for SID: {sid}.")
                            emit('verification_result', {'status': 'success', 'message': 'Verification successful!'}, room=sid)
                            current_session_state['found_live'] = True
                            current_session_state['in_progress'] = False 
                            return 
                        else:
                            print(f"Liveness check negative (not confirmed real) for SID: {sid}. Result: {liveness_result}")
                    else:
                        print(f"No face or inconclusive liveness result by DeepFace for SID: {sid}.")
                except Exception as e:
                    print(f"Liveness check error for SID {sid} on face of {name}: {e}")
            
            if current_session_state.get('found_live', False): # If successful, break from face loop
                break 
    
    except cv2.error as e:
        print(f"OpenCV error processing video frame for SID {sid}: {e}. Likely bad image data.")
    except Exception as e:
        print(f"Generic error processing video frame for SID {sid}: {e}")


@socketio.on('stop_verify')
def handle_stop_verify():
    sid = request.sid
    current_session_state = session_verification_state.get(sid)

    print(f"Verification stop request received for SID: {sid}.")
    if current_session_state and current_session_state.get('in_progress'):
        if not current_session_state.get('found_live', False):
            emit('verification_result', {'status': 'failed', 'message': 'Verification stopped by user.'}, room=sid)
        current_session_state['in_progress'] = False
        print(f"Verification stopped by client for SID: {sid}.")


@socketio.on('disconnect')
def handle_disconnect():
    global uploaded_file_registry # To remove file from TTL registry
    sid = request.sid
    print(f"Client disconnected: {sid}")
    
    filepath_deleted_on_disconnect = None
    # Delete the target image associated with this session from disk
    if sid in session_target_encodings:
        target_data = session_target_encodings.pop(sid) # Remove from session tracking
        filepath_to_delete = target_data.get("filepath")
        if filepath_to_delete and os.path.exists(filepath_to_delete):
            try:
                os.remove(filepath_to_delete)
                print(f"Deleted target image {filepath_to_delete} for SID {sid} on disconnect.")
                filepath_deleted_on_disconnect = filepath_to_delete
            except Exception as e:
                print(f"Error deleting target image {filepath_to_delete} for SID {sid} on disconnect: {e}")
    
    # If a file was deleted from disk, also remove it from the TTL registry
    if filepath_deleted_on_disconnect:
        with uploaded_files_lock:
            # Rebuild registry excluding the file deleted on disconnect
            temp_deque = collections.deque()
            while uploaded_file_registry: # Iterate through current registry
                fp_reg, ts_reg = uploaded_file_registry.popleft()
                if fp_reg != filepath_deleted_on_disconnect: # Keep if not the one deleted
                    temp_deque.append((fp_reg, ts_reg))
            uploaded_file_registry = temp_deque # Assign the filtered deque back
            print(f"Removed {filepath_deleted_on_disconnect} from TTL registry due to disconnect.")

    if sid in session_verification_state:
        session_verification_state.pop(sid)
        print(f"Cleaned up verification state for SID {sid}.")


if __name__ == '__main__':
    print("Starting Flask app with SocketIO...")
    
    # Start the background TTL cleanup worker thread
    ttl_cleanup_worker_thread = threading.Thread(target=background_ttl_cleanup_worker, daemon=True)
    ttl_cleanup_worker_thread.start()
    print("Background TTL cleanup worker thread initiated.")

    print(f"Server will be accessible on port 5000. If on a local network, use this machine's local IP address.")
    print("Make sure your firewall allows connections on port 5000.")
    print("Client-side JavaScript should connect to: http://<YOUR_SERVER_IP>:5000")

    try:
        print("Pre-loading DeepFace models (if necessary)...")
        dummy_img_array = np.zeros((100, 100, 3), dtype=np.uint8) 
        DeepFace.extract_faces(img_path=dummy_img_array, detector_backend='opencv', anti_spoofing=True, enforce_detection=False)
        print("DeepFace model check complete.")
    except Exception as e:
        print(f"Could not pre-load/check DeepFace models: {e}")
        print("Note: DeepFace models might download/initialize on the first actual liveness check, causing an initial delay for the first user.")

    socketio.run(app, host='0.0.0.0', port=5000, debug=True) # Set debug=False for production
