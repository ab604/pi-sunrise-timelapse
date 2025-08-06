#!/bin/bash
# Improved Zero Cam preview script with better error handling
echo "Camera Positioning Preview (Enhanced)"
echo "====================================="

# Check prerequisites
check_camera() {
    echo "Checking camera availability..."
    if ! command -v libcamera-still &> /dev/null; then
        echo "Error: libcamera-still not found. Install with:"
        echo "sudo apt update && sudo apt install libcamera-apps"
        exit 1
    fi
    
    # Quick camera test
    timeout 10 libcamera-hello --list-cameras &>/dev/null
    if [ $? -ne 0 ]; then
        echo "Warning: Camera not detected. Check connections and config file"
        if [ -f "/boot/firmware/config.txt" ]; then
            echo "Ensure 'camera_auto_detect=1' is in /boot/firmware/config.txt"
        elif [ -f "/boot/config.txt" ]; then
            echo "Ensure 'camera_auto_detect=1' is in /boot/config.txt"
        fi
    fi
}

# Create preview directory
mkdir -p /tmp/camera_preview
cd /tmp/camera_preview

# Enhanced HTML with error display
cat > index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Zero Cam Preview</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            margin: 20px; 
            background: #f0f0f0;
        }
        .container { 
            max-width: 800px; 
            margin: 0 auto; 
            background: white; 
            padding: 20px; 
            border-radius: 10px;
        }
        img { 
            max-width: 100%; 
            height: auto; 
            border: 2px solid #333; 
            border-radius: 5px;
        }
        button { 
            padding: 12px 24px; 
            margin: 10px; 
            font-size: 16px; 
            background: #007bff; 
            color: white; 
            border: none; 
            border-radius: 5px; 
            cursor: pointer;
        }
        button:hover { background: #0056b3; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .status { color: #666; font-size: 14px; margin: 10px 0; }
        .error { color: #dc3545; }
        .success { color: #28a745; }
        .settings { 
            margin: 20px 0; 
            padding: 15px; 
            background: #f8f9fa; 
            border-radius: 5px;
        }
        select, input { 
            padding: 5px; 
            margin: 5px; 
            border: 1px solid #ddd; 
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Zero Cam Preview</h1>
        
        <div class="settings">
            <label>Size: 
                <select id="sizeSelect">
                    <option value="640x480">640x480</option>
                    <option value="800x600">800x600</option>
                    <option value="1024x768">1024x768</option>
                    <option value="1920x1080">1920x1080</option>
                </select>
            </label>
            
            <label>Quality: 
                <select id="qualitySelect">
                    <option value="50">50%</option>
                    <option value="75" selected>75%</option>
                    <option value="90">90%</option>
                    <option value="100">100%</option>
                </select>
            </label>
            
            <label>Auto-refresh: 
                <input type="checkbox" id="autoRefresh" checked>
            </label>
        </div>
        
        <div id="imageContainer">
            <img id="preview" src="preview.jpg?t=0" alt="Camera View" 
                 onerror="handleImageError()" onload="handleImageLoad()">
        </div>
        
        <div>
            <button onclick="refreshImage()" id="captureBtn">📸 Take New Photo</button>
            <button onclick="downloadImage()">💾 Download Image</button>
        </div>
        
        <div class="status" id="status">Loading camera preview...</div>
        
        <div id="imageInfo" class="status"></div>
    </div>

    <script>
        let autoRefreshInterval;
        
        async function refreshImage() {
            const btn = document.getElementById('captureBtn');
            const status = document.getElementById('status');
            
            btn.disabled = true;
            btn.textContent = '📸 Capturing...';
            status.textContent = 'Taking new photo...';
            status.className = 'status';
            
            try {
                const size = document.getElementById('sizeSelect').value;
                const quality = document.getElementById('qualitySelect').value;
                
                const response = await fetch(`/capture?size=${size}&quality=${quality}`);
                const result = await response.text();
                
                if (response.ok) {
                    // Force image refresh with timestamp
                    const timestamp = new Date().getTime();
                    const img = document.getElementById('preview');
                    img.src = `preview.jpg?t=${timestamp}`;
                    
                    status.textContent = `Photo captured at ${new Date().toLocaleTimeString()}`;
                    status.className = 'status success';
                } else {
                    status.textContent = `Error: ${result}`;
                    status.className = 'status error';
                }
            } catch (error) {
                status.textContent = `Network error: ${error.message}`;
                status.className = 'status error';
            } finally {
                btn.disabled = false;
                btn.textContent = '📸 Take New Photo';
            }
        }
        
        function handleImageError() {
            const status = document.getElementById('status');
            status.textContent = 'Image failed to load. Try capturing a new photo.';
            status.className = 'status error';
            
            // Show placeholder
            const img = document.getElementById('preview');
            img.style.display = 'none';
            
            const placeholder = document.createElement('div');
            placeholder.id = 'placeholder';
            placeholder.style.cssText = `
                width: 100%; height: 300px; 
                background: #eee; 
                border: 2px dashed #ccc; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                color: #666;
            `;
            placeholder.textContent = 'No image available - click "Take New Photo"';
            
            const container = document.getElementById('imageContainer');
            const existing = document.getElementById('placeholder');
            if (existing) existing.remove();
            container.appendChild(placeholder);
        }
        
        function handleImageLoad() {
            const img = document.getElementById('preview');
            img.style.display = 'block';
            
            const placeholder = document.getElementById('placeholder');
            if (placeholder) placeholder.remove();
            
            // Show image info
            const info = document.getElementById('imageInfo');
            info.textContent = `Image loaded: ${img.naturalWidth}x${img.naturalHeight}`;
        }
        
        function downloadImage() {
            const link = document.createElement('a');
            link.href = 'preview.jpg';
            link.download = `zerocam-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.jpg`;
            link.click();
        }
        
        function setupAutoRefresh() {
            const checkbox = document.getElementById('autoRefresh');
            
            if (checkbox.checked) {
                autoRefreshInterval = setInterval(function() {
                    const timestamp = new Date().getTime();
                    const img = document.getElementById('preview');
                    img.src = `preview.jpg?t=${timestamp}`;
                }, 3000);
            } else {
                clearInterval(autoRefreshInterval);
            }
        }
        
        // Initialize
        document.getElementById('autoRefresh').addEventListener('change', setupAutoRefresh);
        setupAutoRefresh();
        
        // Take initial photo
        setTimeout(refreshImage, 1000);
    </script>
</body>
</html>
EOF

# Enhanced capture script
cat > capture_photo.sh << 'EOF'
#!/bin/bash
LOG_FILE="/tmp/camera_preview/capture.log"

# Parse parameters
SIZE=${1:-"800x600"}
QUALITY=${2:-"75"}

# Extract width and height
WIDTH=$(echo $SIZE | cut -d'x' -f1)
HEIGHT=$(echo $SIZE | cut -d'x' -f2)

echo "$(date): Capturing ${WIDTH}x${HEIGHT} at ${QUALITY}% quality" >> $LOG_FILE

# Capture with error handling
if timeout 15 libcamera-still \
    --width $WIDTH \
    --height $HEIGHT \
    --quality $QUALITY \
    --timeout 2000 \
    --nopreview \
    -o /tmp/camera_preview/preview.jpg 2>>$LOG_FILE; then
    
    if [ -f "/tmp/camera_preview/preview.jpg" ]; then
        echo "$(date): Capture successful" >> $LOG_FILE
        echo "Photo captured successfully"
    else
        echo "$(date): Capture failed - no output file" >> $LOG_FILE
        echo "Error: No image file created"
        exit 1
    fi
else
    echo "$(date): libcamera-still command failed" >> $LOG_FILE
    echo "Error: Camera capture command failed"
    exit 1
fi
EOF

chmod +x capture_photo.sh

# Check camera before starting
check_camera

# Take initial photo
echo "Taking initial photo..."
./capture_photo.sh 800x600 75

# Get IP address
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Camera Preview Ready ==="
echo "View at: http://${PI_IP}:8080"
echo "Features:"
echo "  • Adjustable resolution and quality"
echo "  • Auto-refresh toggle"
echo "  • Download captured images"
echo "  • Error handling and status display"
echo ""
echo "Press Ctrl+C to stop the server"
echo "Check capture.log for camera errors"

# Enhanced Python server
python3 -c "
import http.server
import socketserver
import subprocess
import os
import urllib.parse
from datetime import datetime

class CaptureHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/capture':
            self.capture_photo(parsed_path.query)
        else:
            super().do_GET()

    def capture_photo(self, query_string):
        try:
            # Parse query parameters
            params = urllib.parse.parse_qs(query_string)
            size = params.get('size', ['800x600'])[0]
            quality = params.get('quality', ['75'])[0]
            
            # Run capture script
            result = subprocess.run(
                ['./capture_photo.sh', size, quality],
                capture_output=True,
                text=True,
                timeout=20
            )
            
            if result.returncode == 0:
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(result.stdout.encode())
            else:
                self.send_error(500, f'Capture failed: {result.stderr}')
                
        except subprocess.TimeoutExpired:
            self.send_error(500, 'Camera capture timed out')
        except Exception as e:
            self.send_error(500, f'Server error: {str(e)}')

    def log_message(self, format, *args):
        # Log to file instead of stdout
        with open('/tmp/camera_preview/server.log', 'a') as f:
            f.write(f'{datetime.now()}: {format % args}\n')

print('Starting camera preview server...')
with socketserver.TCPServer(('', 8080), CaptureHandler) as httpd:
    httpd.serve_forever()
"
