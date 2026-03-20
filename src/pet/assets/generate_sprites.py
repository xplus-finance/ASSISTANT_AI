#!/usr/bin/env python3
"""
Pixel Art Sprite Sheet Generator for XPlus Desktop Pet
Generates 5 pets x 6 animations x 4 frames = 120 frames (30 sprite sheets)
Each sprite sheet: 384x96 (4 frames of 96x96 horizontally)
"""

from PIL import Image, ImageDraw
import os
import math

FRAME_SIZE = 96
FRAMES_PER_ANIM = 4
SHEET_WIDTH = FRAME_SIZE * FRAMES_PER_ANIM
SHEET_HEIGHT = FRAME_SIZE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ANIMATIONS = ['idle', 'walk', 'type', 'run', 'sad', 'sleep']
PET_TYPES = ['dog', 'cat', 'robot', 'fox', 'owl']


def create_frame():
    return Image.new('RGBA', (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))


def save_sprite_sheet(frames, pet_type, animation):
    sheet = Image.new('RGBA', (SHEET_WIDTH, SHEET_HEIGHT), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * FRAME_SIZE, 0))
    path = os.path.join(BASE_DIR, pet_type, f'{animation}.png')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    print(f"  Saved: {pet_type}/{animation}.png")


# ===========================================================================
# DRAWING HELPERS
# ===========================================================================

def draw_pixel_circle(draw, cx, cy, r, fill, outline=None):
    """Draw a filled circle (ellipse)."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline)


def draw_ear_triangle(draw, x, y, w, h, fill, outline=None):
    """Draw a triangular ear pointing up."""
    draw.polygon([(x, y + h), (x + w // 2, y), (x + w, y + h)], fill=fill, outline=outline)


def draw_rounded_rect(draw, x1, y1, x2, y2, r, fill, outline=None):
    """Draw a rounded rectangle."""
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline)


def draw_text_pixels(draw, x, y, text, color, scale=1):
    """Draw tiny pixel text - Z characters for sleep."""
    if text == 'z':
        # Small z: 5x5
        for i in range(4 * scale):
            draw.point((x + i, y), fill=color)
            draw.point((x + i, y + 4 * scale), fill=color)
        # diagonal
        for i in range(4 * scale):
            px = x + (3 * scale) - i
            py = y + 1 + i * 3 // (4 if scale == 1 else 3)
            draw.point((px, min(py, y + 3 * scale)), fill=color)


def draw_zzz(draw, x, y, color):
    """Draw zzz sleep indicator."""
    # Three Z's getting bigger
    s = 2
    for i in range(3):
        zx = x + i * 7
        zy = y - i * 6
        sz = s + i
        # horizontal top
        for j in range(sz + 2):
            draw.point((zx + j, zy), fill=color)
        # diagonal
        for j in range(sz):
            draw.point((zx + sz + 1 - j * (sz + 2) // max(sz, 1), zy + 1 + j), fill=color)
        # horizontal bottom
        for j in range(sz + 2):
            draw.point((zx + j, zy + sz + 1), fill=color)


def draw_tear(draw, x, y, color=(100, 150, 255, 220)):
    """Draw a small teardrop."""
    draw.polygon([(x, y), (x - 2, y + 4), (x + 2, y + 4)], fill=color)
    draw.ellipse([x - 2, y + 3, x + 2, y + 6], fill=color)


# ===========================================================================
# DOG SPRITES
# ===========================================================================

def draw_dog_base(draw, cx=48, cy=50, body_y_offset=0, leg_offsets=None,
                  tail_angle=0, head_tilt=0, ear_droop=0, eyes_open=True,
                  is_curled=False, stretch=0):
    """Draw the base dog shape."""
    BROWN = (139, 69, 19, 255)
    LIGHT_BROWN = (210, 105, 30, 255)
    BLACK = (0, 0, 0, 255)
    WHITE = (255, 255, 255, 255)
    NOSE = (50, 30, 20, 255)

    if leg_offsets is None:
        leg_offsets = [0, 0, 0, 0]  # FL, FR, BL, BR

    if is_curled:
        # Curled up sleeping dog
        body_cx, body_cy = cx, cy + 10
        draw.ellipse([body_cx - 22, body_cy - 12, body_cx + 22, body_cy + 14], fill=BROWN, outline=(100, 50, 10, 255))
        draw.ellipse([body_cx - 15, body_cy - 5, body_cx + 10, body_cy + 10], fill=LIGHT_BROWN)
        # Head resting
        head_cx, head_cy = cx - 14, cy
        draw_pixel_circle(draw, head_cx, head_cy, 10, BROWN, outline=(100, 50, 10, 255))
        # Closed eyes
        draw.line([(head_cx - 5, head_cy - 1), (head_cx - 2, head_cy - 1)], fill=BLACK, width=1)
        draw.line([(head_cx + 2, head_cy - 1), (head_cx + 5, head_cy - 1)], fill=BLACK, width=1)
        # Ears flat
        draw.ellipse([head_cx - 12, head_cy - 6, head_cx - 6, head_cy + 2], fill=(120, 60, 15, 255))
        # Nose
        draw.rectangle([head_cx - 1, head_cy + 3, head_cx + 1, head_cy + 5], fill=NOSE)
        # Tail curled around
        draw.arc([body_cx + 5, body_cy - 15, body_cx + 28, body_cy + 5], 0, 270, fill=BROWN, width=3)
        return

    body_w, body_h = 20 + stretch, 15
    body_cx, body_cy = cx, cy + 8 + body_y_offset

    # Body
    draw_rounded_rect(draw, body_cx - body_w, body_cy - body_h,
                      body_cx + body_w, body_cy + body_h, 8, BROWN, outline=(100, 50, 10, 255))
    # Belly
    draw.ellipse([body_cx - body_w + 5, body_cy - 3, body_cx + body_w - 5, body_cy + body_h - 2],
                 fill=LIGHT_BROWN)

    # Legs
    leg_w, leg_h = 5, 14
    leg_positions = [
        (body_cx - body_w + 6, body_cy + body_h - 4),   # FL
        (body_cx - body_w + 14, body_cy + body_h - 4),  # FR
        (body_cx + body_w - 14, body_cy + body_h - 4),  # BL
        (body_cx + body_w - 6, body_cy + body_h - 4),   # BR
    ]
    for i, (lx, ly) in enumerate(leg_positions):
        off = leg_offsets[i]
        draw.rectangle([lx - leg_w // 2 + off, ly, lx + leg_w // 2 + off, ly + leg_h],
                       fill=BROWN, outline=(100, 50, 10, 255))
        # Paw
        draw.ellipse([lx - leg_w // 2 - 1 + off, ly + leg_h - 2, lx + leg_w // 2 + 1 + off, ly + leg_h + 2],
                     fill=LIGHT_BROWN)

    # Tail
    tail_bx = body_cx + body_w - 2
    tail_by = body_cy - body_h + 5
    tail_angle_rad = math.radians(tail_angle)
    tail_ex = tail_bx + int(14 * math.cos(math.radians(-45 + tail_angle)))
    tail_ey = tail_by + int(14 * math.sin(math.radians(-45 + tail_angle)))
    draw.line([(tail_bx, tail_by), (tail_ex, tail_ey)], fill=BROWN, width=3)
    draw_pixel_circle(draw, tail_ex, tail_ey, 2, BROWN)

    # Head
    head_cx = body_cx - body_w + 8
    head_cy = body_cy - body_h - 6 + head_tilt
    head_r = 12
    draw_pixel_circle(draw, head_cx, head_cy, head_r, BROWN, outline=(100, 50, 10, 255))

    # Snout
    draw.ellipse([head_cx - 5, head_cy + 2, head_cx + 5, head_cy + 10], fill=LIGHT_BROWN)
    # Nose
    draw.ellipse([head_cx - 2, head_cy + 3, head_cx + 2, head_cy + 6], fill=NOSE)

    # Eyes
    if eyes_open:
        draw_pixel_circle(draw, head_cx - 5, head_cy - 2, 2, WHITE)
        draw_pixel_circle(draw, head_cx + 5, head_cy - 2, 2, WHITE)
        draw.point((head_cx - 5, head_cy - 2), fill=BLACK)
        draw.point((head_cx - 4, head_cy - 2), fill=BLACK)
        draw.point((head_cx + 5, head_cy - 2), fill=BLACK)
        draw.point((head_cx + 4, head_cy - 2), fill=BLACK)
    else:
        draw.line([(head_cx - 7, head_cy - 2), (head_cx - 3, head_cy - 1)], fill=BLACK, width=1)
        draw.line([(head_cx + 3, head_cy - 2), (head_cx + 7, head_cy - 1)], fill=BLACK, width=1)

    # Ears
    ear_h = 10 - ear_droop
    draw_ear_triangle(draw, head_cx - 12, head_cy - head_r - ear_h + ear_droop, 8, ear_h,
                      BROWN, outline=(100, 50, 10, 255))
    draw_ear_triangle(draw, head_cx + 4, head_cy - head_r - ear_h + ear_droop, 8, ear_h,
                      BROWN, outline=(100, 50, 10, 255))
    # Inner ear
    draw_ear_triangle(draw, head_cx - 10, head_cy - head_r - ear_h + 3 + ear_droop, 4, ear_h - 3,
                      (180, 100, 60, 255))
    draw_ear_triangle(draw, head_cx + 6, head_cy - head_r - ear_h + 3 + ear_droop, 4, ear_h - 3,
                      (180, 100, 60, 255))


def generate_dog():
    print("Generating dog sprites...")

    # IDLE - tail wag
    frames = []
    tail_angles = [-15, 0, 15, 0]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_dog_base(draw, tail_angle=tail_angles[i])
        frames.append(img)
    save_sprite_sheet(frames, 'dog', 'idle')

    # WALK - legs alternate
    frames = []
    walk_legs = [
        [-3, 3, 3, -3],
        [0, 0, 0, 0],
        [3, -3, -3, 3],
        [0, 0, 0, 0],
    ]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_dog_base(draw, leg_offsets=walk_legs[i], tail_angle=10 * (i % 2))
        frames.append(img)
    save_sprite_sheet(frames, 'dog', 'walk')

    # TYPE - paws moving
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        paw_up = [0, -4, 0, 0] if i % 2 == 0 else [-4, 0, 0, 0]
        draw_dog_base(draw, leg_offsets=paw_up, head_tilt=-2)
        # Draw small desk/keyboard
        draw.rectangle([20, 72, 50, 75], fill=(120, 80, 50, 255))
        # Keys
        for k in range(5):
            c = (200, 200, 200, 255) if (k + i) % 2 == 0 else (170, 170, 170, 255)
            draw.rectangle([22 + k * 5, 70, 26 + k * 5, 72], fill=c)
        frames.append(img)
    save_sprite_sheet(frames, 'dog', 'type')

    # RUN - extended stride
    frames = []
    run_legs = [
        [-6, 6, 6, -6],
        [-3, 3, 3, -3],
        [6, -6, -6, 6],
        [3, -3, -3, 3],
    ]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_dog_base(draw, leg_offsets=run_legs[i], stretch=4, ear_droop=4,
                      body_y_offset=-2 if i % 2 == 0 else 0, tail_angle=-20)
        frames.append(img)
    save_sprite_sheet(frames, 'dog', 'run')

    # SAD
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_dog_base(draw, tail_angle=-40 + i * 3, head_tilt=3, ear_droop=5)
        # Tear
        if i in [1, 3]:
            draw_tear(draw, 34, 42 + i)
        frames.append(img)
    save_sprite_sheet(frames, 'dog', 'sad')

    # SLEEP
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_dog_base(draw, is_curled=True)
        # Zzz
        if i >= 1:
            draw_zzz(draw, 55, 38, (100, 100, 200, 180))
        if i >= 2:
            draw_zzz(draw, 62, 30, (100, 100, 200, 140))
        frames.append(img)
    save_sprite_sheet(frames, 'dog', 'sleep')


# ===========================================================================
# CAT SPRITES
# ===========================================================================

def draw_cat_base(draw, cx=48, cy=50, body_y_offset=0, leg_offsets=None,
                  tail_curve=0, head_tilt=0, ear_flat=0, eyes_open=True,
                  is_curled=False, stretch=0, whisker_twitch=0):
    ORANGE = (255, 140, 0, 255)
    DARK_ORANGE = (200, 100, 0, 255)
    YELLOW = (255, 215, 0, 255)
    GREEN = (46, 139, 87, 255)
    BLACK = (0, 0, 0, 255)
    WHITE = (255, 255, 255, 255)
    PINK = (255, 180, 180, 255)

    if leg_offsets is None:
        leg_offsets = [0, 0, 0, 0]

    if is_curled:
        body_cx, body_cy = cx, cy + 12
        draw.ellipse([body_cx - 20, body_cy - 14, body_cx + 20, body_cy + 10], fill=ORANGE, outline=DARK_ORANGE)
        # Stripes
        for s in range(-12, 13, 6):
            draw.line([(body_cx + s, body_cy - 12), (body_cx + s + 3, body_cy + 6)], fill=DARK_ORANGE, width=1)
        # Head tucked
        head_cx, head_cy = cx - 12, cy + 2
        draw_pixel_circle(draw, head_cx, head_cy, 9, ORANGE, outline=DARK_ORANGE)
        # Closed eyes
        draw.arc([head_cx - 6, head_cy - 3, head_cx - 1, head_cy + 1], 0, 180, fill=BLACK, width=1)
        draw.arc([head_cx + 1, head_cy - 3, head_cx + 6, head_cy + 1], 0, 180, fill=BLACK, width=1)
        # Ears
        draw_ear_triangle(draw, head_cx - 10, head_cy - 12, 7, 7, ORANGE, outline=DARK_ORANGE)
        draw_ear_triangle(draw, head_cx + 3, head_cy - 12, 7, 7, ORANGE, outline=DARK_ORANGE)
        # Nose
        draw.polygon([(head_cx, head_cy + 3), (head_cx - 1, head_cy + 1), (head_cx + 1, head_cy + 1)], fill=PINK)
        # Tail over nose
        tail_pts = [(body_cx + 18, body_cy - 5)]
        tail_pts.append((body_cx + 22, body_cy - 12))
        tail_pts.append((body_cx + 15, body_cy - 18))
        tail_pts.append((head_cx + 8, head_cy + 5))
        draw.line(tail_pts, fill=ORANGE, width=3)
        # White tail tip
        draw_pixel_circle(draw, tail_pts[-1][0], tail_pts[-1][1], 2, WHITE)
        return

    body_w, body_h = 18 + stretch, 12
    body_cx, body_cy = cx, cy + 10 + body_y_offset

    # Body
    draw.ellipse([body_cx - body_w, body_cy - body_h, body_cx + body_w, body_cy + body_h],
                 fill=ORANGE, outline=DARK_ORANGE)
    # Stripes on body
    for s in range(-10, 11, 6):
        draw.line([(body_cx + s, body_cy - body_h + 3), (body_cx + s + 2, body_cy + body_h - 3)],
                  fill=DARK_ORANGE, width=1)
    # Belly
    draw.ellipse([body_cx - body_w + 6, body_cy, body_cx + body_w - 6, body_cy + body_h - 1],
                 fill=YELLOW)

    # Legs (thin)
    leg_w, leg_h = 4, 15
    leg_positions = [
        (body_cx - body_w + 5, body_cy + body_h - 5),
        (body_cx - body_w + 12, body_cy + body_h - 5),
        (body_cx + body_w - 12, body_cy + body_h - 5),
        (body_cx + body_w - 5, body_cy + body_h - 5),
    ]
    for i, (lx, ly) in enumerate(leg_positions):
        off = leg_offsets[i]
        draw.rectangle([lx - leg_w // 2 + off, ly, lx + leg_w // 2 + off, ly + leg_h],
                       fill=ORANGE, outline=DARK_ORANGE)
        # Paw
        draw.ellipse([lx - leg_w // 2 - 1 + off, ly + leg_h - 2, lx + leg_w // 2 + 1 + off, ly + leg_h + 2],
                     fill=YELLOW)

    # Tail
    tail_bx = body_cx + body_w - 2
    tail_by = body_cy - 2
    tc = tail_curve
    tail_pts = [
        (tail_bx, tail_by),
        (tail_bx + 10, tail_by - 10 + tc),
        (tail_bx + 16, tail_by - 20 + tc),
        (tail_bx + 12, tail_by - 26 + tc),
    ]
    draw.line(tail_pts, fill=ORANGE, width=3)
    draw_pixel_circle(draw, tail_pts[-1][0], tail_pts[-1][1], 2, WHITE)

    # Head
    head_cx = body_cx - body_w + 6
    head_cy = body_cy - body_h - 5 + head_tilt
    head_r = 11
    draw_pixel_circle(draw, head_cx, head_cy, head_r, ORANGE, outline=DARK_ORANGE)

    # Ears
    ear_h = 10 - ear_flat
    draw_ear_triangle(draw, head_cx - 11, head_cy - head_r - ear_h + ear_flat + 2, 8, ear_h,
                      ORANGE, outline=DARK_ORANGE)
    draw_ear_triangle(draw, head_cx + 3, head_cy - head_r - ear_h + ear_flat + 2, 8, ear_h,
                      ORANGE, outline=DARK_ORANGE)
    # Inner ear
    draw_ear_triangle(draw, head_cx - 9, head_cy - head_r - ear_h + ear_flat + 5, 4, ear_h - 4,
                      PINK)
    draw_ear_triangle(draw, head_cx + 5, head_cy - head_r - ear_h + ear_flat + 5, 4, ear_h - 4,
                      PINK)

    # Eyes
    if eyes_open:
        # Almond eyes
        draw.ellipse([head_cx - 7, head_cy - 4, head_cx - 2, head_cy + 1], fill=WHITE)
        draw.ellipse([head_cx + 2, head_cy - 4, head_cx + 7, head_cy + 1], fill=WHITE)
        # Green iris
        draw.ellipse([head_cx - 6, head_cy - 3, head_cx - 3, head_cy], fill=GREEN)
        draw.ellipse([head_cx + 3, head_cy - 3, head_cx + 6, head_cy], fill=GREEN)
        # Pupil slit
        draw.line([(head_cx - 5, head_cy - 3), (head_cx - 4, head_cy)], fill=BLACK, width=1)
        draw.line([(head_cx + 4, head_cy - 3), (head_cx + 5, head_cy)], fill=BLACK, width=1)
    else:
        draw.arc([head_cx - 7, head_cy - 3, head_cx - 2, head_cy + 2], 0, 180, fill=BLACK, width=1)
        draw.arc([head_cx + 2, head_cy - 3, head_cx + 7, head_cy + 2], 0, 180, fill=BLACK, width=1)

    # Nose
    draw.polygon([(head_cx, head_cy + 4), (head_cx - 2, head_cy + 2), (head_cx + 2, head_cy + 2)], fill=PINK)

    # Whiskers
    wt = whisker_twitch
    draw.line([(head_cx - 3, head_cy + 3), (head_cx - 15, head_cy + wt)], fill=BLACK, width=1)
    draw.line([(head_cx - 3, head_cy + 4), (head_cx - 15, head_cy + 5 + wt)], fill=BLACK, width=1)
    draw.line([(head_cx - 3, head_cy + 5), (head_cx - 15, head_cy + 10 + wt)], fill=BLACK, width=1)
    draw.line([(head_cx + 3, head_cy + 3), (head_cx + 15, head_cy + wt)], fill=BLACK, width=1)
    draw.line([(head_cx + 3, head_cy + 4), (head_cx + 15, head_cy + 5 + wt)], fill=BLACK, width=1)
    draw.line([(head_cx + 3, head_cy + 5), (head_cx + 15, head_cy + 10 + wt)], fill=BLACK, width=1)

    # Mouth
    draw.arc([head_cx - 3, head_cy + 3, head_cx, head_cy + 7], 0, 180, fill=BLACK, width=1)
    draw.arc([head_cx, head_cy + 3, head_cx + 3, head_cy + 7], 0, 180, fill=BLACK, width=1)


def generate_cat():
    print("Generating cat sprites...")

    # IDLE
    frames = []
    tail_curves = [0, -4, 0, 4]
    whisker = [0, -1, 0, 1]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_cat_base(draw, tail_curve=tail_curves[i], whisker_twitch=whisker[i])
        frames.append(img)
    save_sprite_sheet(frames, 'cat', 'idle')

    # WALK
    frames = []
    walk_legs = [
        [-3, 3, 3, -3],
        [-1, 1, 1, -1],
        [3, -3, -3, 3],
        [1, -1, -1, 1],
    ]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_cat_base(draw, leg_offsets=walk_legs[i], tail_curve=i * 2 - 3)
        frames.append(img)
    save_sprite_sheet(frames, 'cat', 'walk')

    # TYPE
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        paw = [0, -5, 0, 0] if i % 2 == 0 else [-5, 0, 0, 0]
        draw_cat_base(draw, leg_offsets=paw, head_tilt=-1)
        draw.rectangle([18, 73, 48, 76], fill=(120, 80, 50, 255))
        for k in range(5):
            c = (200, 200, 200, 255) if (k + i) % 2 == 0 else (170, 170, 170, 255)
            draw.rectangle([20 + k * 5, 71, 24 + k * 5, 73], fill=c)
        frames.append(img)
    save_sprite_sheet(frames, 'cat', 'type')

    # RUN - stretched leap
    frames = []
    run_legs = [
        [-7, 7, 7, -7],
        [-4, 4, 4, -4],
        [7, -7, -7, 7],
        [4, -4, -4, 4],
    ]
    body_y = [-3, -1, -3, -1]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_cat_base(draw, leg_offsets=run_legs[i], stretch=5,
                      body_y_offset=body_y[i], tail_curve=-8)
        frames.append(img)
    save_sprite_sheet(frames, 'cat', 'run')

    # SAD
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_cat_base(draw, tail_curve=10, head_tilt=3, ear_flat=5, whisker_twitch=3)
        if i % 2 == 1:
            draw_tear(draw, 33, 43)
        frames.append(img)
    save_sprite_sheet(frames, 'cat', 'sad')

    # SLEEP
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_cat_base(draw, is_curled=True)
        if i >= 1:
            draw_zzz(draw, 55, 36, (100, 100, 200, 180))
        if i >= 2:
            draw_zzz(draw, 62, 28, (100, 100, 200, 140))
        frames.append(img)
    save_sprite_sheet(frames, 'cat', 'sleep')


# ===========================================================================
# ROBOT SPRITES
# ===========================================================================

def draw_robot_base(draw, cx=48, cy=48, body_y_offset=0, leg_offsets=None,
                    arm_offsets=None, eyes_mode='normal', antenna_blink=False,
                    is_standby=False, jets=False, screen_text=None, sparks=False):
    GRAY = (112, 128, 144, 255)
    LIGHT_GRAY = (169, 169, 169, 255)
    DARK_GRAY = (80, 80, 90, 255)
    CYAN = (0, 206, 209, 255)
    CYAN_DIM = (0, 100, 110, 180)
    BLACK = (0, 0, 0, 255)
    ORANGE = (255, 140, 0, 255)
    YELLOW = (255, 255, 0, 255)
    WHITE = (255, 255, 255, 255)

    if leg_offsets is None:
        leg_offsets = [0, 0]
    if arm_offsets is None:
        arm_offsets = [0, 0]

    eye_color = CYAN_DIM if is_standby else CYAN
    if antenna_blink:
        eye_color = YELLOW

    body_cx, body_cy = cx, cy + 5 + body_y_offset

    # Legs
    for i, side in enumerate([-1, 1]):
        lx = body_cx + side * 10
        ly = body_cy + 18
        lo = leg_offsets[i]
        draw.rectangle([lx - 5, ly, lx + 5, ly + 16 + lo], fill=LIGHT_GRAY, outline=DARK_GRAY)
        # Foot
        draw.rectangle([lx - 7, ly + 14 + lo, lx + 7, ly + 19 + lo], fill=GRAY, outline=DARK_GRAY)
        if jets:
            # Jet flame
            flame_colors = [ORANGE, YELLOW, (255, 80, 0, 200)]
            for j, fc in enumerate(flame_colors):
                draw.rectangle([lx - 3 + j, ly + 19 + lo, lx + 3 - j, ly + 23 + lo + j * 2], fill=fc)

    # Body
    draw_rounded_rect(draw, body_cx - 16, body_cy - 18, body_cx + 16, body_cy + 18, 3, GRAY, outline=DARK_GRAY)
    # Chest plate
    draw_rounded_rect(draw, body_cx - 12, body_cy - 10, body_cx + 12, body_cy + 10, 2, LIGHT_GRAY, outline=DARK_GRAY)
    # Rivets
    for rx, ry in [(-14, -16), (14, -16), (-14, 16), (14, 16)]:
        draw_pixel_circle(draw, body_cx + rx, body_cy + ry, 2, DARK_GRAY)
    # Chest detail - power core
    draw_pixel_circle(draw, body_cx, body_cy, 4, eye_color)
    draw_pixel_circle(draw, body_cx, body_cy, 2, WHITE)

    # Arms
    for i, side in enumerate([-1, 1]):
        ax = body_cx + side * 22
        ay = body_cy - 8 + arm_offsets[i]
        draw.rectangle([ax - 4, ay, ax + 4, ay + 20], fill=LIGHT_GRAY, outline=DARK_GRAY)
        # Hand (claw)
        draw.rectangle([ax - 5, ay + 18, ax + 5, ay + 24], fill=GRAY, outline=DARK_GRAY)
        # Joint
        draw_pixel_circle(draw, ax, ay, 3, DARK_GRAY)

    # Head
    head_cx = body_cx
    head_cy = body_cy - 28
    head_w, head_h = 14, 12
    draw_rounded_rect(draw, head_cx - head_w, head_cy - head_h, head_cx + head_w, head_cy + head_h,
                      3, GRAY, outline=DARK_GRAY)

    # Antenna
    ant_top = head_cy - head_h - 8
    draw.line([(head_cx, head_cy - head_h), (head_cx, ant_top)], fill=DARK_GRAY, width=2)
    ant_color = YELLOW if antenna_blink else CYAN
    draw_pixel_circle(draw, head_cx, ant_top, 3, ant_color)

    # Face/Screen
    draw_rounded_rect(draw, head_cx - 11, head_cy - 8, head_cx + 11, head_cy + 8, 2,
                      (20, 30, 40, 255), outline=DARK_GRAY)

    if eyes_mode == 'normal':
        # Rectangle eyes
        draw.rectangle([head_cx - 8, head_cy - 5, head_cx - 3, head_cy], fill=eye_color)
        draw.rectangle([head_cx + 3, head_cy - 5, head_cx + 8, head_cy], fill=eye_color)
        # Mouth line
        draw.line([(head_cx - 5, head_cy + 4), (head_cx + 5, head_cy + 4)], fill=eye_color, width=1)
    elif eyes_mode == 'happy':
        draw.arc([head_cx - 8, head_cy - 7, head_cx - 3, head_cy], 180, 360, fill=eye_color, width=1)
        draw.arc([head_cx + 3, head_cy - 7, head_cx + 8, head_cy], 180, 360, fill=eye_color, width=1)
        draw.arc([head_cx - 5, head_cy + 1, head_cx + 5, head_cy + 6], 0, 180, fill=eye_color, width=1)
    elif eyes_mode == 'sad':
        # X_X eyes
        draw.line([(head_cx - 8, head_cy - 5), (head_cx - 3, head_cy)], fill=(255, 50, 50, 255), width=1)
        draw.line([(head_cx - 8, head_cy), (head_cx - 3, head_cy - 5)], fill=(255, 50, 50, 255), width=1)
        draw.line([(head_cx + 3, head_cy - 5), (head_cx + 8, head_cy)], fill=(255, 50, 50, 255), width=1)
        draw.line([(head_cx + 3, head_cy), (head_cx + 8, head_cy - 5)], fill=(255, 50, 50, 255), width=1)
        draw.line([(head_cx - 4, head_cy + 5), (head_cx + 4, head_cy + 5)], fill=(255, 50, 50, 255), width=1)
    elif eyes_mode == 'off':
        # Standby - dim rectangles
        draw.rectangle([head_cx - 8, head_cy - 5, head_cx - 3, head_cy], fill=(30, 50, 60, 255))
        draw.rectangle([head_cx + 3, head_cy - 5, head_cx + 8, head_cy], fill=(30, 50, 60, 255))
    elif eyes_mode == 'text':
        # Screen shows text scrolling
        draw.rectangle([head_cx - 8, head_cy - 5, head_cx - 3, head_cy - 3], fill=eye_color)
        draw.rectangle([head_cx - 8, head_cy - 1, head_cx + 2, head_cy + 1], fill=eye_color)
        draw.rectangle([head_cx - 8, head_cy + 3, head_cx + 6, head_cy + 5], fill=eye_color)

    # Sparks effect
    if sparks:
        spark_positions = [(body_cx - 18, body_cy - 5), (body_cx + 20, body_cy + 5),
                           (body_cx - 10, body_cy + 20)]
        for sx, sy in spark_positions:
            draw.line([(sx, sy), (sx + 3, sy - 3)], fill=YELLOW, width=1)
            draw.line([(sx, sy), (sx - 2, sy - 3)], fill=YELLOW, width=1)


def generate_robot():
    print("Generating robot sprites...")

    # IDLE - antenna blinks
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_robot_base(draw, antenna_blink=(i % 2 == 0))
        frames.append(img)
    save_sprite_sheet(frames, 'robot', 'idle')

    # WALK - stiff movement
    frames = []
    walk_legs = [[3, -3], [-1, 1], [-3, 3], [1, -1]]
    walk_arms = [[-3, 3], [0, 0], [3, -3], [0, 0]]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_robot_base(draw, leg_offsets=walk_legs[i], arm_offsets=walk_arms[i])
        frames.append(img)
    save_sprite_sheet(frames, 'robot', 'walk')

    # TYPE - arms moving, screen text
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        arms = [-6 if i % 2 == 0 else 0, -6 if i % 2 == 1 else 0]
        draw_robot_base(draw, arm_offsets=arms, eyes_mode='text')
        # Keyboard
        draw.rectangle([30, 73, 66, 76], fill=(60, 60, 70, 255), outline=(80, 80, 90, 255))
        for k in range(6):
            c = (0, 206, 209, 200) if (k + i) % 2 == 0 else (100, 100, 110, 255)
            draw.rectangle([32 + k * 5, 71, 36 + k * 5, 73], fill=c)
        frames.append(img)
    save_sprite_sheet(frames, 'robot', 'type')

    # RUN - jets from feet
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_robot_base(draw, body_y_offset=-4 + (i % 2) * 2, jets=True,
                        arm_offsets=[-4, -4], eyes_mode='happy')
        frames.append(img)
    save_sprite_sheet(frames, 'robot', 'run')

    # SAD - X_X eyes, sparks
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_robot_base(draw, eyes_mode='sad', sparks=(i % 2 == 0), arm_offsets=[4, 4])
        frames.append(img)
    save_sprite_sheet(frames, 'robot', 'sad')

    # SLEEP - standby
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_robot_base(draw, eyes_mode='off', is_standby=True, antenna_blink=(i == 3))
        if i >= 1:
            draw_zzz(draw, 60, 20, (0, 150, 160, 150))
        frames.append(img)
    save_sprite_sheet(frames, 'robot', 'sleep')


# ===========================================================================
# FOX SPRITES
# ===========================================================================

def draw_fox_base(draw, cx=48, cy=50, body_y_offset=0, leg_offsets=None,
                  tail_pos=0, head_tilt=0, ear_twitch=0, eyes_open=True,
                  is_sleeping=False, stretch=0, tail_between_legs=False):
    RED_ORANGE = (255, 99, 71, 255)
    DARK_RED = (200, 60, 40, 255)
    WHITE = (255, 255, 255, 255)
    BLACK = (0, 0, 0, 255)
    DARK_LEGS = (60, 40, 30, 255)

    if leg_offsets is None:
        leg_offsets = [0, 0, 0, 0]

    if is_sleeping:
        # Fox curled up, nose under tail
        body_cx, body_cy = cx, cy + 12
        draw.ellipse([body_cx - 20, body_cy - 12, body_cx + 20, body_cy + 10], fill=RED_ORANGE, outline=DARK_RED)
        # White belly patch
        draw.ellipse([body_cx - 10, body_cy - 4, body_cx + 8, body_cy + 6], fill=WHITE)
        # Head
        head_cx, head_cy = cx - 14, cy + 2
        # Triangular fox face
        draw.polygon([(head_cx, head_cy + 8), (head_cx - 10, head_cy - 4), (head_cx + 10, head_cy - 4)],
                     fill=RED_ORANGE, outline=DARK_RED)
        draw_pixel_circle(draw, head_cx, head_cy - 2, 8, RED_ORANGE, outline=DARK_RED)
        # White muzzle
        draw.polygon([(head_cx, head_cy + 8), (head_cx - 5, head_cy + 1), (head_cx + 5, head_cy + 1)], fill=WHITE)
        # Closed eyes
        draw.line([(head_cx - 5, head_cy - 2), (head_cx - 2, head_cy - 1)], fill=BLACK, width=1)
        draw.line([(head_cx + 2, head_cy - 2), (head_cx + 5, head_cy - 1)], fill=BLACK, width=1)
        # Ears
        draw_ear_triangle(draw, head_cx - 10, head_cy - 14, 7, 9, RED_ORANGE, outline=DARK_RED)
        draw_ear_triangle(draw, head_cx + 3, head_cy - 14, 7, 9, RED_ORANGE, outline=DARK_RED)
        # Large bushy tail curving over to nose
        tail_pts = [(body_cx + 16, body_cy - 6), (body_cx + 24, body_cy - 16),
                    (body_cx + 14, body_cy - 22), (head_cx + 6, head_cy + 4)]
        draw.line(tail_pts, fill=RED_ORANGE, width=6)
        draw_pixel_circle(draw, tail_pts[-1][0], tail_pts[-1][1], 4, WHITE)
        draw.line(tail_pts, fill=RED_ORANGE, width=3)
        return

    body_w, body_h = 19 + stretch, 12
    body_cx, body_cy = cx, cy + 10 + body_y_offset

    # Body
    draw.ellipse([body_cx - body_w, body_cy - body_h, body_cx + body_w, body_cy + body_h],
                 fill=RED_ORANGE, outline=DARK_RED)
    # White chest
    draw.ellipse([body_cx - body_w + 3, body_cy - 3, body_cx - body_w + 18, body_cy + body_h - 1],
                 fill=WHITE)

    # Legs (dark)
    leg_w, leg_h = 4, 15
    leg_positions = [
        (body_cx - body_w + 5, body_cy + body_h - 5),
        (body_cx - body_w + 12, body_cy + body_h - 5),
        (body_cx + body_w - 12, body_cy + body_h - 5),
        (body_cx + body_w - 5, body_cy + body_h - 5),
    ]
    for i, (lx, ly) in enumerate(leg_positions):
        off = leg_offsets[i]
        draw.rectangle([lx - leg_w // 2 + off, ly, lx + leg_w // 2 + off, ly + leg_h],
                       fill=DARK_LEGS, outline=BLACK)

    # Tail - BUSHY
    tail_bx = body_cx + body_w - 3
    tail_by = body_cy - 4
    if tail_between_legs:
        tail_pts = [(tail_bx, tail_by), (tail_bx - 5, tail_by + 15), (tail_bx - 10, tail_by + 22)]
        draw.line(tail_pts, fill=RED_ORANGE, width=6)
        draw_pixel_circle(draw, tail_pts[-1][0], tail_pts[-1][1], 3, WHITE)
    else:
        tp = tail_pos
        tail_pts = [
            (tail_bx, tail_by),
            (tail_bx + 12, tail_by - 12 + tp),
            (tail_bx + 18, tail_by - 22 + tp),
            (tail_bx + 14, tail_by - 28 + tp),
        ]
        # Bushy tail - draw thick
        draw.line(tail_pts, fill=RED_ORANGE, width=7)
        draw.line(tail_pts, fill=RED_ORANGE, width=5)
        # White tip
        draw_pixel_circle(draw, tail_pts[-1][0], tail_pts[-1][1], 4, WHITE)

    # Head - more triangular/pointed
    head_cx = body_cx - body_w + 6
    head_cy = body_cy - body_h - 5 + head_tilt
    head_r = 10

    draw_pixel_circle(draw, head_cx, head_cy, head_r, RED_ORANGE, outline=DARK_RED)
    # Pointed snout
    draw.polygon([(head_cx, head_cy + 12), (head_cx - 6, head_cy + 3), (head_cx + 6, head_cy + 3)],
                 fill=RED_ORANGE, outline=DARK_RED)
    # White muzzle
    draw.polygon([(head_cx, head_cy + 12), (head_cx - 4, head_cy + 4), (head_cx + 4, head_cy + 4)],
                 fill=WHITE)
    # Nose
    draw.ellipse([head_cx - 2, head_cy + 4, head_cx + 2, head_cy + 7], fill=BLACK)

    # Eyes - narrow/sly
    if eyes_open:
        draw.ellipse([head_cx - 7, head_cy - 3, head_cx - 3, head_cy + 1], fill=(255, 200, 50, 255))
        draw.ellipse([head_cx + 3, head_cy - 3, head_cx + 7, head_cy + 1], fill=(255, 200, 50, 255))
        draw.line([(head_cx - 6, head_cy - 1), (head_cx - 4, head_cy - 1)], fill=BLACK, width=1)
        draw.line([(head_cx + 4, head_cy - 1), (head_cx + 6, head_cy - 1)], fill=BLACK, width=1)
    else:
        draw.line([(head_cx - 7, head_cy - 1), (head_cx - 3, head_cy)], fill=BLACK, width=1)
        draw.line([(head_cx + 3, head_cy - 1), (head_cx + 7, head_cy)], fill=BLACK, width=1)

    # Ears - large and pointed
    et = ear_twitch
    draw_ear_triangle(draw, head_cx - 11, head_cy - head_r - 11 + et, 8, 12,
                      RED_ORANGE, outline=DARK_RED)
    draw_ear_triangle(draw, head_cx + 3, head_cy - head_r - 11 - et, 8, 12,
                      RED_ORANGE, outline=DARK_RED)
    # Inner ear
    draw_ear_triangle(draw, head_cx - 9, head_cy - head_r - 7 + et, 4, 7,
                      (255, 180, 160, 255))
    draw_ear_triangle(draw, head_cx + 5, head_cy - head_r - 7 - et, 4, 7,
                      (255, 180, 160, 255))


def generate_fox():
    print("Generating fox sprites...")

    # IDLE - ears twitch
    frames = []
    ear_t = [0, 2, 0, -2]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_fox_base(draw, ear_twitch=ear_t[i])
        frames.append(img)
    save_sprite_sheet(frames, 'fox', 'idle')

    # WALK - sly trot
    frames = []
    walk_legs = [
        [-3, 3, 3, -3],
        [-1, 1, 1, -1],
        [3, -3, -3, 3],
        [1, -1, -1, 1],
    ]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_fox_base(draw, leg_offsets=walk_legs[i], tail_pos=i * 2 - 3)
        frames.append(img)
    save_sprite_sheet(frames, 'fox', 'walk')

    # TYPE
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        paw = [0, -5, 0, 0] if i % 2 == 0 else [-5, 0, 0, 0]
        draw_fox_base(draw, leg_offsets=paw, head_tilt=-2)
        draw.rectangle([18, 73, 48, 76], fill=(120, 80, 50, 255))
        for k in range(5):
            c = (200, 200, 200, 255) if (k + i) % 2 == 0 else (170, 170, 170, 255)
            draw.rectangle([20 + k * 5, 71, 24 + k * 5, 73], fill=c)
        frames.append(img)
    save_sprite_sheet(frames, 'fox', 'type')

    # RUN - full sprint
    frames = []
    run_legs = [
        [-7, 7, 7, -7],
        [-4, 4, 4, -4],
        [7, -7, -7, 7],
        [4, -4, -4, 4],
    ]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_fox_base(draw, leg_offsets=run_legs[i], stretch=5,
                      body_y_offset=-3 + (i % 2) * 2, tail_pos=-5)
        frames.append(img)
    save_sprite_sheet(frames, 'fox', 'run')

    # SAD - tail between legs
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_fox_base(draw, tail_between_legs=True, head_tilt=3, ear_twitch=3)
        if i % 2 == 1:
            draw_tear(draw, 33, 42)
        frames.append(img)
    save_sprite_sheet(frames, 'fox', 'sad')

    # SLEEP - nose under tail
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_fox_base(draw, is_sleeping=True)
        if i >= 1:
            draw_zzz(draw, 55, 34, (255, 150, 100, 180))
        if i >= 2:
            draw_zzz(draw, 62, 26, (255, 150, 100, 140))
        frames.append(img)
    save_sprite_sheet(frames, 'fox', 'sleep')


# ===========================================================================
# OWL SPRITES
# ===========================================================================

def draw_owl_base(draw, cx=48, cy=48, body_y_offset=0, head_angle=0,
                  wing_pos=0, foot_offsets=None, eyes_open=True, eyes_half=False,
                  is_sleeping=False, is_flying=False, waddle=0):
    BROWN = (139, 105, 20, 255)
    DARK_BROWN = (100, 70, 15, 255)
    GOLD = (255, 215, 0, 255)
    WHEAT = (245, 222, 179, 255)
    BLACK = (0, 0, 0, 255)
    WHITE = (255, 255, 255, 255)
    ORANGE_BEAK = (255, 140, 50, 255)

    if foot_offsets is None:
        foot_offsets = [0, 0]

    body_cx = cx + waddle
    body_cy = cy + 8 + body_y_offset

    if is_flying:
        body_cy = cy + body_y_offset
        # Body
        draw.ellipse([body_cx - 16, body_cy - 18, body_cx + 16, body_cy + 18],
                     fill=BROWN, outline=DARK_BROWN)
        # Chest pattern
        draw.ellipse([body_cx - 10, body_cy - 6, body_cx + 10, body_cy + 14], fill=WHEAT)
        # Chest V marks
        for v in range(3):
            vy = body_cy + v * 5
            draw.line([(body_cx - 4, vy), (body_cx, vy + 3), (body_cx + 4, vy)], fill=DARK_BROWN, width=1)

        # Wings spread
        for side in [-1, 1]:
            wx = body_cx + side * 16
            wing_pts = [
                (wx, body_cy - 8),
                (wx + side * 25, body_cy - 15 + wing_pos),
                (wx + side * 28, body_cy - 5 + wing_pos),
                (wx + side * 22, body_cy + 5 + wing_pos),
                (wx, body_cy + 10),
            ]
            draw.polygon(wing_pts, fill=BROWN, outline=DARK_BROWN)
            # Wing feathers
            for f in range(3):
                fx = wx + side * (8 + f * 6)
                fy = body_cy - 10 + f * 5 + wing_pos
                draw.line([(fx, fy), (fx + side * 5, fy + 8)], fill=DARK_BROWN, width=1)

        # Feet tucked up
        for side in [-1, 1]:
            tx = body_cx + side * 6
            ty = body_cy + 16
            draw.line([(tx, ty), (tx - 3, ty + 4)], fill=DARK_BROWN, width=2)
            draw.line([(tx, ty), (tx, ty + 5)], fill=DARK_BROWN, width=2)
            draw.line([(tx, ty), (tx + 3, ty + 4)], fill=DARK_BROWN, width=2)
    else:
        # Body (taller than wide)
        draw.ellipse([body_cx - 16, body_cy - 20, body_cx + 16, body_cy + 20],
                     fill=BROWN, outline=DARK_BROWN)
        # Chest pattern
        draw.ellipse([body_cx - 10, body_cy - 6, body_cx + 10, body_cy + 16], fill=WHEAT)
        # Chest V pattern marks
        for v in range(3):
            vy = body_cy + v * 5
            draw.line([(body_cx - 4, vy), (body_cx, vy + 3), (body_cx + 4, vy)], fill=DARK_BROWN, width=1)

        # Wings at sides
        for side in [-1, 1]:
            wx = body_cx + side * 14
            wp = wing_pos
            wing_pts = [
                (wx, body_cy - 14),
                (wx + side * 8, body_cy - 5 + wp),
                (wx + side * 10, body_cy + 8 + wp),
                (wx + side * 6, body_cy + 16 + wp),
                (wx, body_cy + 18),
            ]
            draw.polygon(wing_pts, fill=BROWN, outline=DARK_BROWN)

        # Talons
        for i, side in enumerate([-1, 1]):
            tx = body_cx + side * 7 + foot_offsets[i]
            ty = body_cy + 19
            # 3 toes
            draw.line([(tx, ty), (tx - 3, ty + 5)], fill=DARK_BROWN, width=2)
            draw.line([(tx, ty), (tx, ty + 6)], fill=DARK_BROWN, width=2)
            draw.line([(tx, ty), (tx + 3, ty + 5)], fill=DARK_BROWN, width=2)

    # Head
    head_cx = body_cx + head_angle
    head_cy = body_cy - 28 if not is_flying else body_cy - 22
    head_r = 13

    if is_sleeping:
        # Head tucked
        head_cy = body_cy - 22
        head_cx = body_cx + 3

    draw_pixel_circle(draw, head_cx, head_cy, head_r, BROWN, outline=DARK_BROWN)

    # Facial disc
    draw_pixel_circle(draw, head_cx, head_cy + 1, 10, WHEAT)

    # Ear tufts
    for side in [-1, 1]:
        tuft_x = head_cx + side * 9
        draw.polygon([
            (tuft_x, head_cy - head_r + 2),
            (tuft_x + side * 4, head_cy - head_r - 7),
            (tuft_x + side * 1, head_cy - head_r - 2),
        ], fill=BROWN, outline=DARK_BROWN)

    # Eyes - large concentric circles
    if eyes_open and not eyes_half and not is_sleeping:
        for side in [-1, 1]:
            ex = head_cx + side * 5
            ey = head_cy - 1
            draw_pixel_circle(draw, ex, ey, 5, GOLD)
            draw_pixel_circle(draw, ex, ey, 3, BLACK)
            draw_pixel_circle(draw, ex, ey, 1, WHITE)
    elif eyes_half:
        for side in [-1, 1]:
            ex = head_cx + side * 5
            ey = head_cy - 1
            draw_pixel_circle(draw, ex, ey, 5, GOLD)
            draw.rectangle([ex - 5, ey - 5, ex + 5, ey - 1], fill=BROWN)
            draw_pixel_circle(draw, ex, ey + 1, 2, BLACK)
    else:
        # Closed eyes
        for side in [-1, 1]:
            ex = head_cx + side * 5
            ey = head_cy - 1
            draw.arc([ex - 4, ey - 2, ex + 4, ey + 3], 0, 180, fill=DARK_BROWN, width=2)

    # Beak
    draw.polygon([(head_cx, head_cy + 4), (head_cx - 3, head_cy + 2), (head_cx + 3, head_cy + 2)],
                 fill=ORANGE_BEAK, outline=DARK_BROWN)


def generate_owl():
    print("Generating owl sprites...")

    # IDLE - head rotate
    frames = []
    head_angles = [0, 4, 0, -4]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_owl_base(draw, head_angle=head_angles[i])
        frames.append(img)
    save_sprite_sheet(frames, 'owl', 'idle')

    # WALK - waddle
    frames = []
    waddles = [-3, 0, 3, 0]
    foot_offs = [[-2, 2], [0, 0], [2, -2], [0, 0]]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_owl_base(draw, waddle=waddles[i], foot_offsets=foot_offs[i])
        frames.append(img)
    save_sprite_sheet(frames, 'owl', 'walk')

    # TYPE - wing tips tapping
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        wp = -4 if i % 2 == 0 else 0
        draw_owl_base(draw, wing_pos=wp, head_angle=-2)
        draw.rectangle([30, 75, 66, 78], fill=(120, 80, 50, 255))
        for k in range(6):
            c = (200, 200, 200, 255) if (k + i) % 2 == 0 else (170, 170, 170, 255)
            draw.rectangle([32 + k * 5, 73, 36 + k * 5, 75], fill=c)
        frames.append(img)
    save_sprite_sheet(frames, 'owl', 'type')

    # RUN - flying
    frames = []
    wing_positions = [-4, 0, 4, 0]
    fly_y = [-4, -2, -4, -2]
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_owl_base(draw, is_flying=True, wing_pos=wing_positions[i],
                      body_y_offset=fly_y[i])
        frames.append(img)
    save_sprite_sheet(frames, 'owl', 'run')

    # SAD - droopy wings, half-closed eyes
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_owl_base(draw, wing_pos=6, eyes_half=True, head_angle=-1)
        if i % 2 == 1:
            draw_tear(draw, 42, 45)
        frames.append(img)
    save_sprite_sheet(frames, 'owl', 'sad')

    # SLEEP - eyes closed, head tucked
    frames = []
    for i in range(4):
        img = create_frame()
        draw = ImageDraw.Draw(img)
        draw_owl_base(draw, is_sleeping=True, eyes_open=False, wing_pos=2)
        if i >= 1:
            draw_zzz(draw, 58, 22, (180, 160, 80, 180))
        if i >= 2:
            draw_zzz(draw, 65, 14, (180, 160, 80, 140))
        frames.append(img)
    save_sprite_sheet(frames, 'owl', 'sleep')


# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == '__main__':
    print("=" * 50)
    print("XPlus Pet Sprite Sheet Generator")
    print("=" * 50)

    generate_dog()
    generate_cat()
    generate_robot()
    generate_fox()
    generate_owl()

    total = len(PET_TYPES) * len(ANIMATIONS)
    print(f"\nDone! Generated {total} sprite sheets.")
    print(f"Each sheet: {SHEET_WIDTH}x{SHEET_HEIGHT} pixels (4 frames of {FRAME_SIZE}x{FRAME_SIZE})")
