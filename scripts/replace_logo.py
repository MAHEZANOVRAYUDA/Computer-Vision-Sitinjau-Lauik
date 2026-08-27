import re
import os

filepath = r'e:\LPPM\sitinjau-lauik-cv\dashboard\index.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace PUPR Logo base64
content = re.sub(
    r'<img src="data:image/png;base64,[^"]+" alt="PUPR Logo"[^>]+>',
    r'<img src="PU1.png" alt="PUPR Logo" class="logo" style="height:56px;" />',
    content
)

# Also check for UPI YPTK Logo base64 if it exists, replace it with logo-upi-yptk-F_UF5IRd.png
content = re.sub(
    r'<img src="data:image/png;base64,[^"]+" alt="UPI YPTK Logo"[^>]+>',
    r'<img src="logo-upi-yptk-F_UF5IRd.png" alt="UPI YPTK Logo" class="logo" style="height:56px;" />',
    content
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Logos replaced successfully.")
