#!/usr/bin/python3

import ctypes
import os
import configparser
import xdg
import pygame
import i3ipc
import copy
import signal
import sys
import traceback
import pprint
import time
import argparse
import random
import subprocess
import math
from threading import Thread
from PIL import Image, ImageDraw
from xdg.BaseDirectory import xdg_config_home
from contextlib import suppress
from PIL import Image, ImageFilter, ImageEnhance
from utils import *

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--fullscreen", action="store_true",
                    help="run in fullscreen")
parser.add_argument("-m", "--mode", default="filler", help="Workspace allocation logic.\
        sequential: Any new workspace is always the last one, starting from 1000. e.g: [1, 3] -> [1, 3, 1000]\
        filler [default]: Allocate new workspaces by filling gaps in indexes e.g: [1, 3] -> [1, 2, 3]")
parser.add_argument("-w", "--wp", default=None, help="Set your wallpaper to be used to represent new/empty workspaces")

args = parser.parse_args()

pp = pprint.PrettyPrinter(indent=4)

YELLOW = (255, 255, 0)

global_updates_running = True
last_update = 0
global_knowledge = {'active': 0, 'wss': {}, 'ui_cache': {}, 'visible_ws_primary': None, 'out_aliases': {}}

pygame.display.init()
pygame.font.init()
i3 = i3ipc.Connection()

screenshot_lib = 'prtscn.so'
screenshot_lib_path = os.path.dirname(os.path.abspath(__file__)) + os.path.sep + screenshot_lib
grab = ctypes.CDLL(screenshot_lib_path)

def signal_quit(signal, frame):
    print("Shutting down...")
    pygame.display.quit()
    pygame.quit()
    i3.main_quit()
    sys.exit(0)

def signal_reload(signal, frame):
    read_config()

def signal_show(signal, frame):
    global global_updates_running
    # toggles expo view
    if not global_updates_running:
        global_updates_running = True
    else:
        update_state(i3, None)  # for a <1s updated screenshot of the primary ws upon calling
        global_updates_running = False

        # Take a screenshot of the focused window for the window drag overlay
        focused_win = i3.get_tree().find_focused()
        screenshot = grab_screen(x=focused_win.rect.x, y=focused_win.rect.y,
                                 w=focused_win.rect.width, h=focused_win.rect.height)
        global_knowledge['wss'][global_knowledge['active']]['focused_win_screenshot'] = screenshot
        global_knowledge['wss'][global_knowledge['active']]['focused_win_name'] = focused_win.name
        global_knowledge['wss'][global_knowledge['active']]['focused_win_id'] = focused_win.id
        global_knowledge['wss'][global_knowledge['active']]['focused_win_size'] = \
            (focused_win.window_rect.width, focused_win.window_rect.height )

        # Open the expo view on the primary output:
        # 1) Get primary monitor name
        primary_output_name = get_primary_output_name()

        # 2) Get the visible workspace on the primary monitor
        visible_ws_primary = [w.num for w in i3.get_workspaces()
                              if w.visible == True and w.output == primary_output_name][0]
        global_knowledge['visible_ws_primary'] = visible_ws_primary

        # 3) First move to the active ws on the primary output, then create a temporary workspace for the expo view
        i3.command('workspace ' + global_knowledge["wss"][visible_ws_primary]['name'] +
                   '; workspace i3expod-temporary-workspace')

        # 4) And start the UI thread
        ui_thread = Thread(target = show_ui)
        ui_thread.daemon = True
        ui_thread.start()

# Bind signals
signal.signal(signal.SIGINT, signal_quit)
signal.signal(signal.SIGTERM, signal_quit)
signal.signal(signal.SIGHUP, signal_reload)
signal.signal(signal.SIGUSR1, signal_show)

config = configparser.RawConfigParser()

def get_color(section = None, option = None, raw = None):
    if not raw:
        raw = config.get(section, option)

    try:
        return pygame.Color(*raw)
    except (ValueError, TypeError):
        pass

    try:
        return pygame.Color(raw)
    except ValueError:
        pass

    if raw[0] == '#' and len(raw[1:]) == 3:
        try:
            r = int(raw[1], 16)
            g = int(raw[2], 16)
            b = int(raw[3], 16)
            return pygame.Color(r * 16, g * 16, b * 16, 255)
        except ValueError:
            pass

    if raw[0] == '#' and len(raw[1:]) == 6:
        try:
            r = int(raw[1:2], 16)
            g = int(raw[3:4], 16)
            b = int(raw[5:6], 16)
            return pygame.Color(r, g, b, 255)
        except ValueError:
            pass

    raise ValueError

defaults = {
        ('UI', 'bgcolor'): (get_color, get_color(raw = 'gray20')),
        ('UI', 'padding_percent_x'): (config.getint, 5),
        ('UI', 'padding_percent_y'): (config.getint, 5),
        ('UI', 'spacing_percent_x'): (config.getint, 5),
        ('UI', 'spacing_percent_y'): (config.getint, 5),
        ('UI', 'frame_width_px'): (config.getint, 5),
        ('UI', 'frame_active_color'): (get_color, get_color(raw = '#3b4f8a')),
        ('UI', 'frame_inactive_color'): (get_color, get_color(raw = '#43747b')),
        ('UI', 'frame_unknown_color'): (get_color, get_color(raw = '#c8986b')),
        ('UI', 'frame_nonexistant_color'): (get_color, get_color(raw = 'gray30')),
        ('UI', 'tile_active_color'): (get_color, get_color(raw = '#5a6da4')),
        ('UI', 'tile_inactive_color'): (get_color, get_color(raw = '#93afb3')),
        ('UI', 'tile_unknown_color'): (get_color, get_color(raw = '#ffe6d0')),
        ('UI', 'tile_nonexistant_color'): (get_color, get_color(raw = 'gray40')),
        ('UI', 'names_font'): (config.get, 'sans-serif'),
        ('UI', 'names_fontsize'): (config.getint, 25),
        ('UI', 'names_color'): (get_color, get_color(raw = 'white')),
        ('UI', 'names_position'): (config.get, "under"),
        ('UI', 'highlight_percentage'): (config.getint, 20),
}

def read_config():
    config.read(os.path.join(xdg_config_home, "i3expo", "config"))
    # Read custom labels for output names (if any)
    for key in config['OUTPUT_ALIASES']:
        global_knowledge['out_aliases'][key] = config['OUTPUT_ALIASES'][key]
    # Read and override default config if != None
    for option in defaults.keys():
        if not isset(option):
            if defaults[option][1] is None:
                print("Error: Mandatory option " + str(option) + " not set!")
                sys.exit(1)
            config.set(*option, value=defaults[option][1])

def get_config(*option):
    return defaults[option][0](*option)

def isset(option):
    try:
        if defaults[option][0](*option) == "None":
            return False
        return True
    except ValueError:
        return False

def grab_screen(x=None, y=None, w=None, h=None):
    size = w * h
    objlength = size * 3    # RGB has 3 channels... (R, G, B)

    grab.getScreen.argtypes = []
    result = (ctypes.c_ubyte*objlength)()

    grab.getScreen(x, y, w, h, result)
    pil = Image.frombuffer('RGB', (w, h), result, 'raw', 'RGB', 0, 1)
    #draw = ImageDraw.Draw(pil)
    #draw.text((100,100), 'abcde')
    return pygame.image.fromstring(pil.tobytes(), pil.size, pil.mode)

def update_workspace(workspace, screenshot=None):
    if workspace.num not in global_knowledge["wss"].keys():
        global_knowledge["wss"][workspace.num] = {
                'name': None,
                'screenshot': None,
                'windows': {},
                'size': (0, 0),
                'output': "",
                'focused_win_screenshot': None,
                'focused_win_size': None
        }

    global_knowledge["wss"][workspace.num]['size'] = (workspace.rect.width, workspace.rect.height)
    global_knowledge["wss"][workspace.num]['name'] = workspace.name
    global_knowledge["wss"][workspace.num]['screenshot'] = screenshot
    if hasattr(workspace, 'ipc_data') and 'output' in workspace.ipc_data.keys():
        global_knowledge["wss"][workspace.num]['output'] = workspace.ipc_data['output']

    global_knowledge["active"] = workspace.num

def init_knowledge():
    root = i3.get_tree()
    for workspace in root.workspaces():
        update_workspace(workspace)
    # all outputs but the virtual ones
    global_knowledge["outputs"] = [o for o in i3.get_outputs() if o.name.find('xroot') < 0]

def update_state(i3, e):
    global last_update

    time_delta = time.time() - last_update

    if not global_updates_running:
        return False
    if time_delta < 0.2:  # This should be >= your compositor fade time
        return False

    root = i3.get_tree()
    window = root.find_focused()
    current_workspace = window.workspace()

    # Remove leftover desktops
    i3_active_wss = root.workspaces()
    deleted = []
    for num in global_knowledge["wss"].keys():
        if num not in [w.num for w in i3_active_wss]:
            deleted.append(num)
    deleted.sort()  # make sure we're deleting the right items while iterating
    deleted.reverse()
    for num in deleted:
        del(global_knowledge["wss"][num])

    # Take a screenshot and update the active workspace
    screenshot = grab_screen(x=current_workspace.rect.x, y=current_workspace.rect.y,
                             w=current_workspace.rect.width, h=current_workspace.rect.height)
    update_workspace(current_workspace, screenshot)

    # Make sure this function isn't called too frequently
    reset_update_timer(i3, e)

def get_hovered_frame(mpos, frames):
    for frame in frames.keys():
        if frames[frame]['ul'][0] < mpos[0] < frames[frame]['br'][0] \
                and frames[frame]['ul'][1] < mpos[1] < frames[frame]['br'][1]:
            return frame
    return None

def gen_active_win_overlay(rectangle, alpha=255):
    # Calculate active border overlay
    win_pad = int(max((rectangle.height * 2) / 100, (rectangle.width * 2) / 100))
    win_pad = win_pad + 1 if win_pad % 2 != 0 else win_pad
    lightmask = pygame.Surface((rectangle.width + win_pad, rectangle.height + win_pad),
            pygame.SRCALPHA, 32).convert_alpha()
    lightmask_position = (rectangle.x - int(win_pad/2), rectangle.y - int(win_pad/2))
    lightmask.fill(YELLOW + (alpha,))
    return lightmask, lightmask_position

def show_ui():
    global global_updates_running

    FPS = 60

    clock = pygame.time.Clock()

    workspaces = global_knowledge["wss"]
    outputs = global_knowledge["outputs"]

    # Get monitor size
    monitor_size = (pygame.display.Info().current_w, pygame.display.Info().current_h)

    # Calculate grid size in a more efficient way taking into account orientation:
    # Vertical screens take about 1/3 of the horizontal size so we can fit more frames in a row.
    # BUT the exact proportions (w / (h / (w / h))) can't be used because with any gap between frames 
    # we can't really fit any more than two vertical frames, hence tmp += 1/2
    tmp = 0
    for num in global_knowledge["wss"].keys():
        w = global_knowledge["wss"][num]['size'][0]
        h = global_knowledge["wss"][num]['size'][1]
        a = 0
        if h > w:
            # tmp += (w / (h / (w / h) ))  # exact
            tmp += 1/2                     # any gap approximation
        else:
            tmp += 1
    for o in outputs:
        w = o.rect.width
        h = o.rect.height
        if h > w:
            # tmp += (w / (h / (w / h) ))
            tmp += 1/2
        else:
            tmp += 1

    grid_x = grid_y = math.ceil(math.sqrt(tmp))
    grid_size = math.ceil(math.sqrt(len(workspaces) + len(outputs)))
    # print("GRID SIZE: {} x {} ".format(grid_size, grid_size), "EFFICIENT SIZE: {} x {}".format(grid_x, grid_y))

    frame_thickness = get_config('UI', 'frame_width_px')

    frame_active_color = get_config('UI', 'frame_active_color')
    frame_inactive_color = get_config('UI', 'frame_inactive_color')
    frame_unknown_color = get_config('UI', 'frame_unknown_color')
    frame_nonexistant_color = get_config('UI', 'frame_nonexistant_color')
    
    tile_active_color = get_config('UI', 'bgcolor')
    tile_inactive_color = get_config('UI', 'bgcolor')
    tile_unknown_color = get_config('UI', 'tile_unknown_color')
    tile_nonexistant_color = get_config('UI', 'tile_nonexistant_color')
    
    names_font = get_config('UI', 'names_font')
    names_fontsize = get_config('UI', 'names_fontsize')
    names_color = get_config('UI', 'names_color')

    highlight_percentage = get_config('UI', 'highlight_percentage')

    # Create screen surface and set display options
    screen_mode = pygame.FULLSCREEN if args.fullscreen else pygame.RESIZABLE
    screen = pygame.display.set_mode(size=(monitor_size[0], monitor_size[1]), flags=screen_mode, depth=0, display=0)
    screen.set_alpha(None)
    pygame.display.set_caption('i3expo-ng')

    # Usable screen space (if windowed it won't match monitor_size)
    screen_w = screen.get_width()
    screen_h = screen.get_height()

    # Padding/margin for tiles
    pad_w = round(screen_w * get_config('UI', 'padding_percent_x') / 100)
    pad_h = round(screen_h * get_config('UI', 'padding_percent_y') / 100)

    # Gap between tiles (do not confuse with frames)
    tiles_gap_w = round(screen_w * get_config('UI', 'spacing_percent_x') / 100)
    tiles_gap_h = round(screen_h * get_config('UI', 'spacing_percent_y') / 100)

    # Outer and inner tiles size (draw outer then inner to get the frame)
    tiles_outer_w = round((screen_w - 2 * pad_w - tiles_gap_w * (grid_x - 1)) / grid_x)
    tiles_outer_h = round((screen_h - 2 * pad_h - tiles_gap_h * (grid_y - 1)) / grid_y)
    tiles_inner_w = tiles_outer_w - 2 * frame_thickness
    tiles_inner_h = tiles_outer_h - 2 * frame_thickness

    # Gap between frames
    frames_gap_w = tiles_outer_w + tiles_gap_w
    frames_gap_h = tiles_outer_h + tiles_gap_h

    # Thumbnails for ? and +
    thumb_missing = pygame.Surface((monitor_size[0], monitor_size[1]), pygame.SRCALPHA, 32) 
    thumb_missing = thumb_missing.convert_alpha()
    thumb_new = thumb_missing.copy()
    qm = pygame.font.SysFont('sans-serif', 550).render('?', True, (150, 150, 150))
    plss = pygame.font.SysFont('sans-serif', 550).render('+', True, (200, 200, 200))
    qm_size = qm.get_rect().size
    origin_x = round((monitor_size[0] - qm_size[0])/2)
    origin_y = round((monitor_size[1] - qm_size[1])/2)
    thumb_missing.blit(qm, (origin_x, origin_y))

    # if a wallpaper was specified, use that as a background for thumb_new
    if args.wp is not None:
        if 'wp_img' not in global_knowledge['ui_cache'].keys():
            im = Image.open(args.wp)
            en = ImageEnhance.Brightness(im)
            wp_img = en.enhance(0.4)
            wp_img = wp_img\
                    .resize((monitor_size[0], monitor_size[1]), Image.NEAREST)\
                    .filter(ImageFilter.GaussianBlur(radius=20))
            wp_img = pygame.image.fromstring(wp_img.tobytes(), wp_img.size, wp_img.mode)
            global_knowledge['ui_cache']['wp_img'] = wp_img
        wp_img = global_knowledge['ui_cache']['wp_img']
        thumb_new.blit(wp_img, (0, 0))

    thumb_new.blit(plss, (origin_x, origin_y))  # Then draw the + sign

    font = pygame.font.SysFont(names_font, names_fontsize)

    # Get existing workspaces indexes
    wss_idx = [int(k) for k in global_knowledge["wss"].keys()] 
    # Sort workspace indexes by aspect ratio (landscape then portrait)
    wss_idx.sort(key=lambda x: global_knowledge['wss'][x]['size'][1])

    # Generate one new/empty ws for each display output available:
    new_wss_output = {}
    tmp = []
    if args.mode == "sequential":
        r = max(1000, wss_idx[-1])  # or r = 1000
    elif args.mode == "filler":
        r = 1
    for out in outputs:
        while r in wss_idx + tmp:
            r += 1
        new_wss_output[r] = out
        tmp.append(r)

    # Sort NEW workspace indexes by aspect ratio (portrait then landscape) and append them to the list of workspaces
    tmp.sort(key=lambda x: new_wss_output[x].rect.width)
    wss_idx.extend(tmp)
    del tmp

    # Desktop index matrix for keyboard navigation
    kbd_grid = [-1 for _ in range(grid_y)]
    for i in range(len(kbd_grid)):
        kbd_grid[i] = [-1 for _ in range(grid_size * grid_size)]
        
    # Thumbnails and frames cache
    thumb_cache = {i: None for i in wss_idx}
    frame_template = {'active': False,
            'mouseoff': None,
            'mouseon': None,
            'mouseondrag': None,
            'ul': (0, 0),
            'br': (0, 0)} 
    frames = {i: frame_template.copy() for i in wss_idx}

    def draw_grid():
        screen.fill(get_config('UI', 'bgcolor'))
        wss_idx_todo = wss_idx.copy()

        for y in range(grid_y):
            tile_last_x = 0
            for x in range(grid_x * grid_x):
                # Origin point for next tile will be after the last one on this row
                tile_origin_x = tile_last_x + tiles_gap_w if tile_last_x != 0 else pad_w
                tile_origin_y = pad_h + frames_gap_h * y

                # Extract the next workspace index and place it on the matrix
                index = None
                for i, idx in enumerate(wss_idx_todo):
                    tiles_outer_w_dyn = tiles_outer_w
                    tiles_inner_w_dyn = tiles_inner_w

                    # Is it an existing ws or a new one to be created?
                    ws_width = global_knowledge["wss"][idx]['size'][0] if idx in global_knowledge["wss"].keys() \
                        else new_wss_output[idx].rect.width
                    ws_height = global_knowledge["wss"][idx]['size'][1] if idx in global_knowledge["wss"].keys() \
                        else new_wss_output[idx].rect.height

                    # Resize frame width for vertical workspaces
                    if ws_height > ws_width:
                        factor = (ws_height / (ws_width / (ws_height / ws_width) ))
                        tiles_outer_w_dyn = round(tiles_outer_w_dyn / factor)
                        tiles_inner_w_dyn = tiles_outer_w_dyn - 2 * frame_thickness

                    # If it fits on the row, place it and remove its index from the todo list
                    if tile_origin_x + tiles_outer_w_dyn <= screen_w - pad_w:
                        index = idx
                        del wss_idx_todo[i]
                        break

                if index is None:
                    break

                tile_last_x = tile_origin_x + tiles_outer_w_dyn
                kbd_grid[y][x] = index
                frames[index]['ul'] = (tile_origin_x, tile_origin_y)
                frames[index]['br'] = (tile_origin_x + tiles_outer_w_dyn, tile_origin_y + tiles_outer_h)

                # Different properties for different kinds of thumbnails
                if global_knowledge['active'] == index:
                    tile_color = tile_active_color
                    frame_color = frame_active_color
                    image = global_knowledge["wss"][index]['screenshot']
                elif index in global_knowledge["wss"].keys() and\
                     global_knowledge["wss"][index]['screenshot']:
                    tile_color = tile_inactive_color
                    frame_color = frame_inactive_color
                    image = global_knowledge["wss"][index]['screenshot']
                elif index in global_knowledge["wss"].keys():
                    tile_color = tile_unknown_color
                    frame_color = frame_unknown_color
                    image = thumb_missing
                else:
                    tile_color = tile_nonexistant_color
                    frame_color = frame_nonexistant_color
                    image = thumb_new

                # Draw frame
                screen.fill(frame_color, (tile_origin_x, tile_origin_y, tiles_outer_w_dyn, tiles_outer_h,))
                # Draw tile
                screen.fill(tile_color, (tile_origin_x + frame_thickness, tile_origin_y + frame_thickness,
                                         tiles_inner_w_dyn, tiles_inner_h,))

                # Calculate thumbnail placement and size
                image_w = image.get_rect().size[0]
                image_h = image.get_rect().size[1]
                crop = None

                # Resize / crop the image to fit the tile
                if image_w > image_h and tiles_inner_w_dyn < tiles_inner_h:
                    result_x = tiles_inner_w
                    result_y = tiles_inner_h
                    offset_x = round((tiles_inner_w - result_x) / 2)
                    offset_y = 0
                    crop = (tiles_inner_w/2 - tiles_inner_w_dyn/2, 0, tiles_inner_w_dyn, tiles_inner_h)
                else:
                    result_x = tiles_inner_w_dyn
                    result_y = tiles_inner_h
                    offset_x = 0
                    offset_y = round((tiles_inner_h - result_y) / 2)

                # Rescale the screenshot as a thumbnail and cache it, or use the cached result if present
                if thumb_cache[index] is not None:
                    image = thumb_cache[index]
                else:
                    image = pygame.transform.smoothscale(image, (result_x, result_y))
                    thumb_cache[index] = image

                # Put the right label (workspace name or output name for the ws to be created on)
                if index in global_knowledge["wss"].keys():
                    name = global_knowledge["wss"][index]['name']
                    out_name = global_knowledge["wss"][index]['output']
                    if out_name.lower() in global_knowledge['out_aliases'].keys():
                        out_name = global_knowledge['out_aliases'][out_name.lower()]
                    name += " (" + out_name + ")"
                else:
                    name = new_wss_output[index].name
                    if name.lower() in global_knowledge['out_aliases'].keys():
                        name = global_knowledge['out_aliases'][name.lower()]

                # Calculate label / caption
                name = font.render(name, True, names_color)
                name_width = name.get_rect().size[0]
                name_x = tile_origin_x + round((tiles_outer_w_dyn- name_width) / 2)
                name_y = tile_origin_y + tiles_outer_h + round(tiles_outer_h * 0.02)

                if get_config('UI', 'names_position') == "inside":
                    name_size = name.get_size()
                    name_bg_margin_x = 8
                    name_bg_margin_y = 8
                    name_size = (name_size[0] + name_bg_margin_x, name_size[1] + name_bg_margin_y)
                    name_bg = pygame.Surface(name_size)
                    name_bg.fill((0, 0, 0))
                    name_bg.blit(name, (name_bg_margin_x/2, name_bg_margin_x/2))
                    name = name_bg
                    name_y = tile_origin_y + tiles_inner_h - name.get_rect().size[1]

                # DRAW the screenshot as a thumbnail
                screen.blit(image, (tile_origin_x + frame_thickness + offset_x,
                                    tile_origin_y + frame_thickness + offset_y), crop)

                # Draw the label / caption
                screen.blit(name, (name_x, name_y))

                # Calculate mouseon, mouseoff, mousedrag overlays and cache them
                if frames[index]['mouseon'] is None:
                    mouseoff = screen.subsurface((tile_origin_x, tile_origin_y, tiles_outer_w_dyn, tiles_outer_h)).copy()
                    lightmask = pygame.Surface((tiles_outer_w_dyn, tiles_outer_h), pygame.SRCALPHA, 32)
                    lightmask.convert_alpha()
                    lightmask_drag = lightmask.copy()
                    lightmask.fill((255,255,255,255 * highlight_percentage / 100))
                    lightmask_drag.fill((128,128,255,255 * highlight_percentage / 100))
                    mouseon = mouseoff.copy()
                    mouseondrag = mouseoff.copy()
                    mouseon.blit(lightmask, (0, 0))
                    mouseondrag.blit(lightmask_drag, (0, 0))
                    frames[index]['mouseon'] = mouseon.copy()
                    frames[index]['mouseondrag'] = mouseondrag.copy()
                    frames[index]['mouseoff'] = mouseoff.copy()


    pygame.display.flip()

    # set initial status
    active_frame = None
    last_active_frame = wss_idx[0]
    rectangle_dragging = False
    running = True
    use_mouse = True
    grid_dirty_flag = False

    # For keyboard navigation
    col_idx = 0
    row_idx = 0

    # Focused window thumb overlay to be dragged over to workspaces
    focused_win_screenshot = global_knowledge['wss'][global_knowledge['active']]['focused_win_screenshot']
    focused_win_size = global_knowledge['wss'][global_knowledge['active']]['focused_win_size']

    # Get screenshot aspect ratio and scale it to be a bit smaller than the workspaces thumb
    focused_win_thumb = None
    rectangle = None
    if focused_win_screenshot is not None and focused_win_size is not None and focused_win_size[1] > 0:
        ar = min(focused_win_size) / max(focused_win_size)
        factor = 1.5
        if focused_win_size[1] > focused_win_size[0]: 
            rh = int(tiles_inner_h/factor)
            rw = int(rh * ar)
        else:
            rw = int(tiles_inner_w/factor)
            rh = int(rw * ar)
        del factor

        rectangle = pygame.rect.Rect(screen.get_width() - rw - int(pad_w/2),
                                     screen.get_height() - rh - int(pad_h/2),
                                     rw,
                                     rh)

        focused_win_thumb = pygame.transform.smoothscale(focused_win_screenshot, (rectangle.width, rectangle.height))

        with suppress(KeyError):
            focused_win_id = global_knowledge['wss'][global_knowledge['active']]['focused_win_id']

    # Draw grid
    draw_grid()

    # Draw focused window thumbnail overlay border
    if focused_win_thumb is not None:
        lightmask, lightmask_position = gen_active_win_overlay(rectangle, alpha=0)
        screen.blit(lightmask, lightmask_position)
        speed = int(300 / FPS)
        for i in range(0, 100, speed):
            alpha = int(255 * i / 100)
            f = focused_win_thumb.convert_alpha()
            f.fill((255, 255, 255, alpha), None, pygame.BLEND_RGBA_MULT)
            lightmask.fill(YELLOW + (int(alpha/8),))
            screen.blit(lightmask, lightmask_position)
            screen.blit(f, rectangle) 
            pygame.display.flip()
            clock.tick(FPS)

    # Main loop: redraw screen and check status
    while running and not global_updates_running and pygame.display.get_init():

        # Avoid trailing effect when dragging the focused window preview over a workspace
        if rectangle_dragging:
            draw_grid()

        jump = False
        move_win = False
        kbdmove = (0, 0)
        cmd = ""

        # Check for user interaction (via keyboard or mouse)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEMOTION:
                use_mouse = True
                if rectangle_dragging:
                    mouse_x, mouse_y = event.pos
                    rectangle.x = mouse_x + offset_x
                    rectangle.y = mouse_y + offset_y
            elif event.type == pygame.KEYDOWN:
                use_mouse = False
                if event.key == pygame.K_UP or event.key == pygame.K_k:
                    kbdmove = (0, -1)
                if event.key == pygame.K_DOWN or event.key == pygame.K_j:
                    kbdmove = (0, 1)
                if event.key == pygame.K_LEFT or event.key == pygame.K_h:
                    kbdmove = (-1, 0)
                if event.key == pygame.K_RIGHT or event.key == pygame.K_l:
                    kbdmove = (1, 0)
                if event.key == pygame.K_RETURN:
                    jump = True
                if event.key == pygame.K_ESCAPE:
                    running = False
                pygame.event.clear()
                break

            elif event.type == pygame.MOUSEBUTTONUP:
                use_mouse = True
                if event.button == 1:
                    if rectangle_dragging:
                        move_win = True
                    jump = True  
                    rectangle_dragging = False
                pygame.event.clear()
                break

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if rectangle is not None and rectangle.collidepoint(event.pos):
                        rectangle_dragging = True
                        mouse_x, mouse_y = event.pos
                        offset_x = rectangle.x - mouse_x
                        offset_y = rectangle.y - mouse_y

        # Determine which frame is being hovered either with the mouse or keyboard selection
        if use_mouse:
            mpos = pygame.mouse.get_pos()
            af = get_hovered_frame(mpos, frames)
            active_frame = af if af is not None else last_active_frame
            last_active_frame = active_frame
        elif kbdmove != (0, 0):
            if kbdmove[0] != 0:
                tmp = col_idx + kbdmove[0]
                col_idx = tmp if tmp < len(kbd_grid[0]) else col_idx
                col_idx = 0 if col_idx < 0 else col_idx
            elif kbdmove[1] != 0:
                tmp = row_idx + kbdmove[1]
                row_idx = tmp if tmp < len(kbd_grid) else row_idx
                row_idx = 0 if row_idx < 0 else row_idx

            active_frame = kbd_grid[row_idx][col_idx]

            if active_frame < 0:
                row_idx = col_idx = 0
                active_frame = kbd_grid[row_idx][col_idx]

            last_active_frame = active_frame

        # If the active window is moved to a workspace
        if move_win:
            if focused_win_id is None: break

            # Move active container to selected workspace (name if it already exists, number if it is to be created)
            if active_frame in global_knowledge["wss"].keys():
                cmd += '[con_id=\"' + str(focused_win_id) + '\"] move container to workspace ' + \
                       global_knowledge["wss"][active_frame]['name'] + ";"
            else:
                cmd += '[con_id=\"' + str(focused_win_id) + '\"] move container to workspace ' + \
                       str(active_frame) + ";"

        # If the user release left click on a workspace, jump to it
        if jump:
            # Create a new empty workspace on the requested output
            if active_frame not in global_knowledge["wss"].keys():
                cmd += "workspace " + str(active_frame) + ";"
                cmd += 'move workspace to output ' + new_wss_output[active_frame].name + ';'

            # Jump back to the visible ws on primary output to preserve back_and_forth behaviour
            cmd += 'workspace ' + global_knowledge["wss"][global_knowledge['visible_ws_primary']]['name'] + ';'

            # Jump to the requested workspace (by its name if already exists, by its number if it's created anew)
            if active_frame in global_knowledge["wss"].keys():
                cmd += 'workspace ' + global_knowledge["wss"][active_frame]['name']
            else:
                cmd += 'workspace ' + str(active_frame)
            break

        # DRAW mouseoff, mouseon, mouseondrag overlays
        for frame in frames.keys():
            if frames[frame]['active'] and not frame == active_frame:
                screen.blit(frames[frame]['mouseoff'], frames[frame]['ul'])
                frames[frame]['active'] = False
                grid_dirty_flag = True
        if active_frame: # and not frames[active_frame]['active']:
            screen.blit(frames[active_frame]['mouseon'], frames[active_frame]['ul'])
            grid_dirty_flag = True
            if rectangle_dragging:
                screen.blit(frames[active_frame]['mouseondrag'], frames[active_frame]['ul'])
            frames[active_frame]['active'] = True

        if (rectangle_dragging or grid_dirty_flag) and rectangle is not None:
            grid_dirty_flag = False
            lightmask, lightmask_position = gen_active_win_overlay(rectangle)
            # DRAW active window border overlay
            screen.blit(lightmask, lightmask_position)
            # DRAW active window thumbnail
            screen.blit(focused_win_thumb, rectangle) if focused_win_thumb is not None else None

        pygame.display.update()
        clock.tick(FPS)

    pygame.display.quit()
    pygame.display.init()

    # If quitting without jump, jump back to the active workspace on the primary output
    if not jump:
        cmd = 'workspace ' + global_knowledge["wss"][global_knowledge['visible_ws_primary']]['name'] + ';'

    i3.command(cmd)

    # Unlock the global updates
    global_updates_running = True


def reset_update_timer(i3, e):
    global last_update
    last_update = time.time()   


if __name__ == '__main__':

    read_config()
    init_knowledge()
    update_state(i3, None)

    i3.on('window::new', update_state)
    i3.on('window::close', update_state)
    i3.on('window::move', update_state)
    i3.on('window::floating', update_state)
    i3.on('window::fullscreen_mode', update_state)
    # i3.on('window::focus', update_state)

    # Reset time counter so that the update thread does not take a screenshot 
    # while transitioning from one workspace to another, resulting in a dirty screenshot
    # if you use a compositor with fading enabled
    i3.on('workspace', reset_update_timer)

    i3_thread = Thread(target = i3.main)
    i3_thread.daemon = True
    i3_thread.start()

    while True:
        time.sleep(1)
        update_state(i3, None)
