import os
import re

html_path = r"e:/Projects/FYNELLIS/Code/html/lastest/full.html"
assets_dir = r"e:/Projects/FYNELLIS/Code/html/lastest/assets"
SIZE_LIMIT = 500 * 1024 # 500 KB limit for inlining

with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# I will find all SVG blocks and check if they are very large
# and if they correspond to a file in assets

svg_pattern = re.compile(r'<svg[^>]+>.*?</svg>', re.DOTALL)

def process_svg_block(match):
    svg_block = match.group(0)
    if len(svg_block) > SIZE_LIMIT:
        print(f"Large SVG block found ({len(svg_block)} bytes). Checking for match in assets...")
        # Try to find which file this belongs to
        for filename in os.listdir(assets_dir):
            if filename.endswith('.svg') and filename != 'vector_1.svg': # Keep vector_1 inlined as requested
                asset_path = os.path.join(assets_dir, filename)
                with open(asset_path, 'r', encoding='utf-8') as f:
                    asset_content = f.read()
                
                # We need to be careful with comparing because I added classes/styles
                # Let's just check if the bulk of the content (IDs, paths) matches
                if len(asset_content) > 1000 and asset_content[:500] in svg_block and asset_content[-500:] in svg_block:
                    print(f"Match found for {filename}. Reverting to <img> tag.")
                    # Try to reconstruct the <img> tag
                    # Earlier I had <img class="..." src="assets/..." />
                    # Let's see if I can extract the class I added.
                    class_match = re.search(r'class="([^"]+)"', svg_block)
                    img_class = class_match.group(1) if class_match else ""
                    
                    return f'<img class="{img_class}" src="assets/{filename}"/>'
    
    return svg_block

new_html_content = svg_pattern.sub(process_svg_block, html_content)

if new_html_content != html_content:
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html_content)
    print("Reverted large SVGs.")
else:
    print("No large SVGs found to revert.")
