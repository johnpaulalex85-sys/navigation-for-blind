// Global variables for dashboard
const socket = io();
let localStream = null;
let captureInterval = null;
let lastInstructionText = "";
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let frameRateCount = 0;
let lastFpsTime = Date.now();

// Navigation State
let nodes = [];
let edges = [];
let rooms = [];
let activePath = [];
let currentSource = "Entrance Lobby"; // Default start
let currentDestination = "";

// Drawing
const mapImage = new Image();
mapImage.src = "/static/uploads/floor_plan.png";

// DOM Elements
const video = document.getElementById('webcam-video');
const overlayCanvas = document.getElementById('canvas-overlay');
const overlayCtx = overlayCanvas.getContext('2d');

const mapCanvas = document.getElementById('navigation-map-canvas');
const mapCtx = mapCanvas.getContext('2d');

const socketStatus = document.getElementById('socket-status');
const fpsCounter = document.getElementById('fps-counter');
const instructionDisplay = document.getElementById('navigation-instruction-text');
const detectionsList = document.getElementById('detections-list');
const ocrList = document.getElementById('ocr-list');
const safetyBanner = document.getElementById('safety-alert-banner');
const safetyText = document.getElementById('safety-alert-text');
const micBtn = document.getElementById('btn-mic');
const ttsVolume = document.getElementById('tts-volume');
const ttsRate = document.getElementById('tts-rate');

const destDisplay = document.getElementById('dest-display-val');
const locDisplay = document.getElementById('loc-display-val');

// Hidden Canvas for webcam downsampling
const hiddenCanvas = document.createElement('canvas');
const hiddenCtx = hiddenCanvas.getContext('2d');

// TTS System
const synth = window.speechSynthesis;

function speak(text, interrupt = false) {
    if (!text) return;
    if (synth.speaking && !interrupt) return;
    
    if (interrupt) synth.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.volume = parseFloat(ttsVolume.value);
    utterance.rate = parseFloat(ttsRate.value);
    
    const voices = synth.getVoices();
    const englishVoice = voices.find(v => v.lang.startsWith('en'));
    if (englishVoice) utterance.voice = englishVoice;
    
    synth.speak(utterance);
    console.log("Speech output: " + text);
}

// Websocket Events
socket.on('connect', () => {
    socketStatus.className = "badge bg-success fs-6 px-3 py-2";
    socketStatus.innerHTML = '<i class="fa-solid fa-circle-check me-2"></i>Online';
    speak("Dashboard connected.");
});

socket.on('disconnect', () => {
    socketStatus.className = "badge bg-danger fs-6 px-3 py-2";
    socketStatus.innerHTML = '<i class="fa-solid fa-circle-nodes me-2"></i>Offline';
    speak("Server connection offline.");
});

// YOLO Detections Sockets
socket.on('object_detection', (data) => {
    const detections = data.detections || [];
    const alerts = data.alerts || [];
    
    // Bounding boxes drawn on animation loop
    window.activeDetections = detections;
    
    // Update detections list UI
    detectionsList.innerHTML = '';
    if (detections.length === 0) {
        detectionsList.innerHTML = '<li>No obstacles detected</li>';
    } else {
        detections.forEach(det => {
            const li = document.createElement('li');
            li.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-warning me-2"></i>${det.class} (${det.distance}m, ${det.position})`;
            detectionsList.appendChild(li);
        });
    }
    
    // Critical alert warnings
    if (alerts.length > 0) {
        const topAlert = alerts[0];
        safetyBanner.classList.remove('d-none');
        safetyText.innerText = topAlert;
        speak(topAlert, true);
    } else {
        safetyBanner.classList.add('d-none');
    }
    
    // FPS counting
    frameRateCount++;
    const now = Date.now();
    if (now - lastFpsTime >= 1000) {
        fpsCounter.innerText = `FPS: ${frameRateCount}`;
        frameRateCount = 0;
        lastFpsTime = now;
    }
});

// Live OCR matching for location updates
socket.on('ocr_detection', (data) => {
    const ocr_results = data.ocr || [];
    window.activeOcr = ocr_results;
    
    ocrList.innerHTML = '';
    if (ocr_results.length === 0) {
        ocrList.innerHTML = '<li>Scanning for signs...</li>';
        return;
    }
    
    ocr_results.forEach(res => {
        const li = document.createElement('li');
        li.innerHTML = `<i class="fa-solid fa-circle-info text-info me-2"></i>"${res.text}"`;
        ocrList.appendChild(li);
        
        // Auto Localizer: Match detected camera text against database rooms list
        const textLower = res.text.toLowerCase().trim();
        
        // Search if text corresponds to a room number or node name
        const matchRoom = rooms.find(r => r.room_number.toLowerCase() === textLower || 
                                           r.node_name.toLowerCase().includes(textLower));
        
        if (matchRoom) {
            const newLocation = matchRoom.node_name;
            if (newLocation !== currentSource) {
                currentSource = newLocation;
                locDisplay.innerText = newLocation;
                speak(`Location updated. You are near ${newLocation}. Re-calculating path.`, true);
                
                // Replanning dynamically
                requestRoute();
            }
        }
    });
});

// A* Route Updates
socket.on('navigation_route', (data) => {
    activePath = data.path || [];
    const instructions = data.instructions || [];
    
    drawNavigationMap();
    
    if (instructions.length > 0) {
        const topInstruction = instructions[0];
        instructionDisplay.innerText = topInstruction;
        
        if (topInstruction !== lastInstructionText) {
            lastInstructionText = topInstruction;
            speak(topInstruction);
        }
    }
});

socket.on('navigation_error', (data) => {
    const err = data.error || "Pathfinder error.";
    instructionDisplay.innerText = err;
    speak(err);
});

// Page Initialization
window.addEventListener('DOMContentLoaded', async () => {
    // 1. Fetch map structure from DB APIs
    try {
        const resNodes = await fetch('/api/nodes');
        nodes = await resNodes.json();
        
        const resEdges = await fetch('/api/edges');
        edges = await resEdges.json();
        
        const resRooms = await fetch('/api/rooms');
        rooms = await resRooms.json();
        
        console.log("Graph loaded:", {nodes, edges, rooms});
        
        // Set default source to first node name if available
        if (nodes.length > 0) {
            currentSource = nodes[0].node_name;
            locDisplay.innerText = currentSource;
        }
        
        // Draw base blueprint
        mapImage.onload = () => {
            drawNavigationMap();
        };
        drawNavigationMap();
    } catch(err) {
        console.error("Error loading map API:", err);
    }
    
    // 2. Read target destination from url query (?dest=102)
    const urlParams = new URLSearchParams(window.location.search);
    const dest = urlParams.get('dest');
    if (dest) {
        currentDestination = dest;
        destDisplay.innerText = "Room " + dest;
        
        // Wait briefly for connection before requesting path
        setTimeout(() => {
            requestRoute();
        }, 1000);
    } else {
        speak("Awaiting destination command.");
    }
});

// Drawing Visual Graph & Path on blueprint image
function drawNavigationMap() {
    mapCtx.clearRect(0, 0, mapCanvas.width, mapCanvas.height);
    
    // Draw blueprint
    if(mapImage.complete && mapImage.naturalWidth !== 0) {
        mapCtx.drawImage(mapImage, 0, 0, mapCanvas.width, mapCanvas.height);
    } else {
        // Grid fallback
        mapCtx.fillStyle = '#1b1d28';
        mapCtx.fillRect(0, 0, mapCanvas.width, mapCanvas.height);
        mapCtx.strokeStyle = 'rgba(255,255,255,0.05)';
        for(let i=0; i<mapCanvas.width; i+=40) {
            mapCtx.beginPath(); mapCtx.moveTo(i, 0); mapCtx.lineTo(i, mapCanvas.height); mapCtx.stroke();
        }
        for(let j=0; j<mapCanvas.height; j+=40) {
            mapCtx.beginPath(); mapCtx.moveTo(0, j); mapCtx.lineTo(mapCanvas.width, j); mapCtx.stroke();
        }
    }
    
    // Draw background edges (gray)
    mapCtx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    mapCtx.lineWidth = 3;
    edges.forEach(edge => {
        const src = nodes.find(n => n.id === edge.source_node);
        const dest = nodes.find(n => n.id === edge.destination_node);
        if (src && dest) {
            mapCtx.beginPath();
            mapCtx.moveTo(src.x_coordinate, src.y_coordinate);
            mapCtx.lineTo(dest.x_coordinate, dest.y_coordinate);
            mapCtx.stroke();
        }
    });

    // Draw active A* route path (thick neon cyan)
    if (activePath.length > 1) {
        mapCtx.strokeStyle = '#00f0ff';
        mapCtx.lineWidth = 6;
        mapCtx.beginPath();
        mapCtx.moveTo(activePath[0].x, activePath[0].y);
        for(let idx = 1; idx < activePath.length; idx++) {
            mapCtx.lineTo(activePath[idx].x, activePath[idx].y);
        }
        mapCtx.stroke();
    }
    
    // Draw Nodes
    nodes.forEach(node => {
        mapCtx.beginPath();
        mapCtx.arc(node.x_coordinate, node.y_coordinate, 7, 0, 2 * Math.PI);
        
        // Highlight current position or destination
        if(node.node_name === currentSource) {
            mapCtx.fillStyle = '#ff3131'; // Red flashing user location
            // Draw extra pulsing aura
            mapCtx.arc(node.x_coordinate, node.y_coordinate, 15, 0, 2 * Math.PI);
            mapCtx.strokeStyle = 'rgba(255, 49, 49, 0.4)';
            mapCtx.lineWidth = 2;
            mapCtx.stroke();
        } else if (node.node_name === currentDestination || 
                   (rooms.find(r => r.room_number === currentDestination && r.node_id === node.id))) {
            mapCtx.fillStyle = '#00f0ff'; // Cyan target destination
        } else {
            mapCtx.fillStyle = '#39ff14'; // Standard Green node
        }
        mapCtx.fill();
        
        mapCtx.fillStyle = '#fff';
        mapCtx.font = '10px Outfit';
        mapCtx.fillText(node.node_name, node.x_coordinate + 10, node.y_coordinate + 3);
    });
}

function requestRoute() {
    if(!currentSource || !currentDestination) return;
    socket.emit('navigation_update', {
        source: currentSource,
        destination: currentDestination
    });
}

function stopNavigation() {
    activePath = [];
    currentDestination = "";
    destDisplay.innerText = "None";
    instructionDisplay.innerText = "Navigation stopped.";
    speak("Navigation cancelled.");
    drawNavigationMap();
}

function repeatInstruction() {
    if(lastInstructionText) {
        speak(lastInstructionText, true);
    } else {
        speak("No instructions loaded.");
    }
}

// Camera Streaming
async function toggleCamera() {
    const cameraBtn = document.getElementById('btn-camera');
    
    if (localStream) {
        stopFrameStreaming();
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
        video.srcObject = null;
        cameraBtn.innerHTML = '<i class="fa-solid fa-camera"></i>Open Camera';
        cameraBtn.className = "btn btn-accessible btn-accessible-primary";
        speak("Camera stopped.");
        overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    } else {
        try {
            speak("Activating camera...");
            const constraints = {
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: "environment"
                },
                audio: false
            };
            localStream = await navigator.mediaDevices.getUserMedia(constraints);
            video.srcObject = localStream;
            
            video.onloadedmetadata = () => {
                overlayCanvas.width = video.videoWidth;
                overlayCanvas.height = video.videoHeight;
                requestAnimationFrame(drawVideoOverlays);
                startFrameStreaming();
            };
            
            cameraBtn.innerHTML = '<i class="fa-solid fa-video-slash"></i>Close Camera';
            cameraBtn.className = "btn btn-accessible btn-accessible-secondary";
            speak("Camera active.");
        } catch (err) {
            console.error(err);
            speak("Failed to open camera.");
        }
    }
}

function startFrameStreaming() {
    if (captureInterval) clearInterval(captureInterval);
    hiddenCanvas.width = 640;
    hiddenCanvas.height = 480;
    
    captureInterval = setInterval(() => {
        if (!localStream || video.paused || video.ended) return;
        hiddenCtx.drawImage(video, 0, 0, hiddenCanvas.width, hiddenCanvas.height);
        const base64Img = hiddenCanvas.toDataURL('image/jpeg', 0.60);
        socket.emit('video_frame', { image: base64Img });
    }, 180); // ~5-6 FPS
}

function stopFrameStreaming() {
    if (captureInterval) {
        clearInterval(captureInterval);
        captureInterval = null;
    }
}

// Drawing YOLO bounding boxes on camera overlay
function drawVideoOverlays() {
    if (!localStream || video.paused || video.ended) {
        overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
        return;
    }
    
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    
    // Draw YOLO
    if (window.activeDetections) {
        window.activeDetections.forEach(det => {
            const [x1, y1, x2, y2] = det.bbox;
            const w = x2 - x1;
            const h = y2 - y1;
            
            overlayCtx.strokeStyle = det.distance <= 1.5 ? '#ff3131' : '#00f0ff';
            overlayCtx.lineWidth = 3;
            overlayCtx.strokeRect(x1, y1, w, h);
            
            overlayCtx.fillStyle = det.distance <= 1.5 ? '#ff3131' : '#00f0ff';
            overlayCtx.font = 'bold 15px Outfit';
            const label = `${det.class} (${det.distance}m)`;
            const textW = overlayCtx.measureText(label).width;
            
            overlayCtx.fillRect(x1 - 1, y1 - 22, textW + 8, 22);
            overlayCtx.fillStyle = '#000';
            overlayCtx.fillText(label, x1 + 4, y1 - 6);
        });
    }
    
    // Draw OCR Boxes
    if (window.activeOcr) {
        window.activeOcr.forEach(ocr => {
            const [x1, y1, x2, y2] = ocr.bbox;
            overlayCtx.strokeStyle = '#ffdf00';
            overlayCtx.lineWidth = 2;
            overlayCtx.strokeRect(x1, y1, x2 - x1, y2 - y1);
            
            overlayCtx.fillStyle = '#ffdf00';
            overlayCtx.font = '12px Outfit';
            overlayCtx.fillText(ocr.text, x1, y1 - 4);
        });
    }
    
    requestAnimationFrame(drawVideoOverlays);
}

// Microphone Voice commands
async function toggleMicRecording() {
    if (isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>Press to Speak';
        micBtn.className = "btn btn-accessible btn-accessible-secondary mic-btn";
    } else {
        try {
            speak("Listening...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };
            
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const formData = new FormData();
                formData.append('audio', audioBlob, 'command.webm');
                
                speak("Analyzing command...");
                try {
                    const res = await fetch('/voice-command', {
                        method: 'POST',
                        body: formData
                    });
                    const result = await res.json();
                    
                    speak("Transcribed: " + result.transcription);
                    
                    if (result.command === "navigate" && result.target) {
                        const targetRoom = result.target.toLowerCase();
                        // Find matching room
                        const match = rooms.find(r => r.room_number.toLowerCase() === targetRoom || 
                                                      r.node_name.toLowerCase().includes(targetRoom));
                        
                        if (match) {
                            currentDestination = match.room_number;
                            destDisplay.innerText = "Room " + match.room_number;
                            speak(`Selected Room ${match.room_number} as destination.`);
                            requestRoute();
                        } else {
                            speak(`Room ${result.target} not found on map.`);
                        }
                    } else if (result.command === "stop") {
                        stopNavigation();
                    } else if (result.command === "where_am_i") {
                        speak(`You are near ${currentSource}. ` + lastInstructionText);
                    } else {
                        speak("Instruction not recognized.");
                    }
                } catch (err) {
                    speak("Voice transcription error.");
                }
                
                stream.getTracks().forEach(track => track.stop());
            };
            
            mediaRecorder.start();
            isRecording = true;
            micBtn.innerHTML = '<i class="fa-solid fa-square"></i>Stop Listening';
            micBtn.className = "btn btn-accessible btn-accessible-danger mic-btn active";
        } catch (err) {
            speak("Microphone access blocked.");
        }
    }
}

// Spacebar controls
window.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && e.target === document.body) {
        e.preventDefault();
        toggleMicRecording();
    }
});
