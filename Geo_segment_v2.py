import os, random, math
from PIL import Image, ImageDraw

def _rand_color_one():
    return tuple(random.randint(0, 255) for _ in range(3))

def _interp(p, q, t):
    return (p[0] + (q[0]-p[0])*t, p[1] + (q[1]-p[1])*t)

def _triangle_strips(v0, v1, v2, n):
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
        num_slices = random.randint(2, 8)  # ← now 2..8 only
        filled_color = _rand_color_one()
        colors = [filled_color if random.choice([True, False]) else (255, 255, 255)
                  for _ in range(num_slices)]

        img = Image.new("RGB", image_size, "white")
        draw = ImageDraw.Draw(img)
        shape_type = random.choice(["circle", "rectangle", "square", "triangle"])

        if shape_type == "circle":
            # True pie slices
            cx, cy = (W/2, H/2)
            r = min(W, H)/2 - margin
            start = 90
            step = 360 / num_slices
            box = (cx - r, cy - r, cx + r, cy + r)
            for k in range(num_slices):
                draw.pieslice(box, start, start + step, fill=colors[k], outline="black")
                start += step

        elif shape_type in ("rectangle", "square"):
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
            draw.rectangle(bbox_rect, outline="black")

        else:  # triangle
            x0, y0, x1, y1 = bbox
            v0 = ((x0 + x1)/2, y0)  # top
            v1 = (x0, y1)          # bottom-left
            v2 = (x1, y1)          # bottom-right
            for k, quad in enumerate(_triangle_strips(v0, v1, v2, num_slices)):
                draw.polygon(quad, fill=colors[k], outline="black")
            draw.polygon([v0, v1, v2], outline="black")

        img.save(os.path.join(folder_path, f"image_{i}.jpg"), quality=95)

    print(f"{n} images have been saved in the folder: {folder_path}")

# Example:
# generate_images(500, "path")
