import os

file_path = 'e:/Projects/FYNELLIS/Code/html/lastest/full.html'
size = os.path.getsize(file_path)
print(f"File size: {size} bytes")

with open(file_path, 'r', encoding='utf-8') as f:
    content_start = f.read(2000)
    print("Start of file:")
    print(content_start)
    
    # Check for large blocks
    f.seek(0)
    content = f.read()
    print(f"Total length: {len(content)}")
    
    import re
    fonts = re.findall(r'url\(data:font/[^)]+\)', content)
    print(f"Found {len(fonts)} embedded fonts.")
    for i, font in enumerate(fonts):
        print(f"Font {i} length: {len(font)}")

    images_in_css = re.findall(r'url\(data:image/[^)]+\)', content)
    print(f"Found {len(images_in_css)} embedded images in CSS.")
    for i, img in enumerate(images_in_css):
        print(f"CSS Image {i} length: {len(img)}")
