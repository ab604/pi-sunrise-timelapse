#!/bin/bash
# Another vibe coded script for testing the Zero Cam
# Claude, prompted by Alistair Bailey 2025-07-08
echo "Camera Positioning Preview (Simple Refresh)"
echo "=============================================="
mkdir -p /tmp/camera_preview

# Create HTML with cache-busting
cat > /tmp/camera_preview/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Camera Positioning</title>
    <style>
        body { font-family: Arial; text-align: center; margin: 20px; }
        img { max-width: 90%; border: 2px solid #333; }
        button { padding: 10px 20px; margin: 10px; font-size: 16px; }
        .status { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <h1>Position Your Camera</h1>
    <img id="preview" src="preview.jpg" alt="Camera View">
    <br>
    <button onclick="refreshImage()">Take New Photo</button>
    <p class="status" id="status">Click button to capture new photo</p>

    <script>
        async function refreshImage() {
            document.getElementById('status').textContent = 'Taking new photo...';

            try {
                // Trigger new photo capture
                const response = await fetch('/capture');
                if (response.ok) {
                    // Force image refresh with timestamp
                    const timestamp = new Date().getTime();
                    const img = document.getElementById('preview');
                    img.src = `preview.jpg?t=${timestamp}`;

                    img.onload = function() {
                        document.getElementById('status').textContent = 'Photo updated at ' + new Date().toLocaleTimeString();
                    };
                } else {
                    document.getElementById('status').textContent = 'Error capturing photo';
                }
            } catch (error) {
                document.getElementById('status').textContent = 'Error: ' + error.message;
            }
        }

        // Auto-refresh image every 2 seconds to show file changes
        setInterval(function() {
            const timestamp = new Date().getTime();
            document.getElementById('preview').src = `preview.jpg?t=${timestamp}`;
        }, 2000);
    </script>
</body>
</html>
EOF

# Create simple capture endpoint
cat > /tmp/camera_preview/capture_photo.sh << 'EOF'
#!/bin/bash
libcamera-still --width 800 --height 800 --quality 75 --timeout 1000 --nopreview -o /tmp/camera_preview/preview.jpg 2>/dev/null
echo "Photo captured at $(date)"
EOF

chmod +x /tmp/camera_preview/capture_photo.sh

# Take initial photo
echo "Taking initial positioning photo..."
libcamera-still --width 800 --height 800 --quality 75 --timeout 1000 --nopreview -o /tmp/camera_preview/preview.jpg 2>/dev/null

PI_IP=$(hostname -I | awk '{print $1}')
echo "View at: http://${PI_IP}:8080"
echo "Click 'Take New Photo' for fresh images"
echo "Press Ctrl+C when done positioning"

cd /tmp/camera_preview

# Start server with capture endpoint
python3 -c "
import http.server
import socketserver
import subprocess
import os
from urllib.parse import urlparse

class CaptureHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/capture':
            self.capture_photo()
        else:
            super().do_GET()

    def capture_photo(self):
        try:
            subprocess.run(['/tmp/camera_preview/capture_photo.sh'],
                          timeout=10, check=True)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Photo captured successfully')
        except Exception as e:
            self.send_error(500, f'Capture Error: {str(e)}')

with socketserver.TCPServer(('', 8080), CaptureHandler) as httpd:
    httpd.serve_forever()
"
