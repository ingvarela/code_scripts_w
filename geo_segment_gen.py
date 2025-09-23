import os, random
from PIL import Image, ImageDraw

def _rand_color():  # RGB 0-255
    return tuple(random.randint(0, 255) for _ in range(3))

def _interp(p, q, t):  # linear interpolation between two points
    return (p[0] + (q[0]-p[0])*t, p[1] + (q[1]-p[1])*t)

def _triangle_strips(v0, v1, v2, n):
    # Split triangle into n horizontal-ish strips parallel to base v1-v2
    strips = []
    for i in range(n):
        t1, t2 = i/n, (i+1)/n
        a1, b1 = _interp(v0, v1, t1), _interp(v0, v2, t1)
        a2, b2 = _interp(v0, v1, t2), _interp(v0, v2, t2)
        strips.append([a1, b1, b2, a2])
    return strips

def generate_images(n, folder_path, image_size=(400, 400), margin=20):
    os.makedirs(folder_path, exist_ok=True)
    W, H = image_size
    bbox = (margin, margin, W-margin, H-margin)

    for i in range(1, n+1):
        num_slices = random.randint(2, 12)
        colors = [_rand_color() if random.choice([True, False]) else (255, 255, 255) for _ in range(num_slices)]

        img = Image.new("RGB", image_size, "white")
        draw = ImageDraw.Draw(img)

        shape_type = random.choice(["circle", "rectangle", "square", "triangle"])

        if shape_type == "circle":
            # Pie slices
            start = 90
            step = 360 / num_slices
            for k in range(num_slices):
                end = start + step
                draw.pieslice(bbox, start, end, fill=colors[k], outline="black")
                start = end

        elif shape_type in ("rectangle", "square"):
            # Square: force bbox to be square centered
            if shape_type == "square":
                side = min(W, H) - 2*margin
                x0 = (W - side)//2
                y0 = (H - side)//2
                bbox_rect = (x0, y0, x0+side, y0+side)
            else:
                bbox_rect = bbox

            x0, y0, x1, y1 = bbox_rect
            horizontal = random.choice([True, False])
            if horizontal:
                h = (y1 - y0) / num_slices
                for k in range(num_slices):
                    yA, yB = y0 + k*h, y0 + (k+1)*h
                    draw.rectangle([x0, yA, x1, yB], fill=colors[k], outline="black")
            else:
                w = (x1 - x0) / num_slices
                for k in range(num_slices):
                    xA, xB = x0 + k*w, x0 + (k+1)*w
                    draw.rectangle([xA, y0, xB, y1], fill=colors[k], outline="black")
            # Draw outer border once (cleaner edge)
            draw.rectangle(bbox_rect, outline="black", width=1)

        else:  # triangle
            # Upward triangle inside bbox
            x0, y0, x1, y1 = bbox
            v0 = ((x0 + x1)/2, y0)      # top
            v1 = (x0, y1)                # bottom-left
            v2 = (x1, y1)                # bottom-right
            strips = _triangle_strips(v0, v1, v2, num_slices)
            for k, quad in enumerate(strips):
                draw.polygon(quad, fill=colors[k], outline="black")
            # Outer border
            draw.polygon([v0, v1, v2], outline="black")

        img.save(os.path.join(folder_path, f"image_{i}.jpg"), quality=95)
    print(f"{n} images have been saved in the folder: {folder_path}")

# Example
# generate_images(500, "path")
