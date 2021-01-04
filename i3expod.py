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
from threading import Thread
from PIL import Image, ImageDraw

from xdg.BaseDirectory import xdg_config_home

pp = pprint.PrettyPrinter(indent=4)

global_updates_running = True
global_knowledge = {'active': 0, 'wss': {}}

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
    if not global_updates_running:
        global_updates_running = True
    else:
        # i3.command('workspace i3expod-temporary-workspace')
        global_updates_running = False
        ui_thread = Thread(target = show_ui)
        ui_thread.daemon = True
        ui_thread.start()

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
  
    #except Exception as e:
    #    print traceback.format_exc()

defaults = {
        ('Capture', 'screenshot_width'): (config.getint, pygame.display.Info().current_w),
        ('Capture', 'screenshot_height'): (config.getint, pygame.display.Info().current_h),
        ('Capture', 'screenshot_offset_x'): (config.getint, 0),
        ('Capture', 'screenshot_offset_y'): (config.getint, 0),

        ('UI', 'window_width'): (config.getint, pygame.display.Info().current_w),
        ('UI', 'window_height'): (config.getint, pygame.display.Info().current_h),
        ('UI', 'bgcolor'): (get_color, get_color(raw = 'gray20')),
        ('UI', 'workspaces'): (config.getint, None),
        ('UI', 'grid_x'): (config.getint, None),
        ('UI', 'grid_y'): (config.getint, None),
        ('UI', 'padding_percent_x'): (config.getint, 5),
        ('UI', 'padding_percent_y'): (config.getint, 5),
        ('UI', 'spacing_percent_x'): (config.getint, 5),
        ('UI', 'spacing_percent_y'): (config.getint, 5),
        ('UI', 'frame_width_px'): (config.getint, 5),
        ('UI', 'frame_active_color'): (get_color, get_color(raw = '#3b4f8a')),
        ('UI', 'frame_inactive_color'): (get_color, get_color(raw = '#43747b')),
        ('UI', 'frame_unknown_color'): (get_color, get_color(raw = '#c8986b')),
        ('UI', 'frame_empty_color'): (get_color, get_color(raw = 'gray60')),
        ('UI', 'frame_nonexistant_color'): (get_color, get_color(raw = 'gray30')),
        ('UI', 'tile_active_color'): (get_color, get_color(raw = '#5a6da4')),
        ('UI', 'tile_inactive_color'): (get_color, get_color(raw = '#93afb3')),
        ('UI', 'tile_unknown_color'): (get_color, get_color(raw = '#ffe6d0')),
        ('UI', 'tile_empty_color'): (get_color, get_color(raw = 'gray80')),
        ('UI', 'tile_nonexistant_color'): (get_color, get_color(raw = 'gray40')),
        ('UI', 'names_show'): (config.getboolean, 'True'),
        ('UI', 'names_font'): (config.get, 'sans-serif'),
        ('UI', 'names_fontsize'): (config.getint, 25),
        ('UI', 'names_color'): (get_color, get_color(raw = 'white')),
        ('UI', 'thumb_stretch'): (config.getboolean, 'False'),
        ('UI', 'highlight_percentage'): (config.getint, 20),
        ('UI', 'switch_to_empty_workspaces'): (config.getboolean, 'False')
}

def read_config():
    config.read(os.path.join(xdg_config_home, "i3expo", "config"))
    for option in defaults.keys():
        if not isset(option):
            if defaults[option][1] == None:
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
    objlength = size * 3

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
                'size': (1920, 1080)
        }

    if screenshot is not None:
        global_knowledge["wss"][workspace.num]['size'] = (screenshot.get_width(), screenshot.get_height())
    global_knowledge["wss"][workspace.num]['name'] = workspace.name
    global_knowledge["wss"][workspace.num]['screenshot'] = screenshot
    global_knowledge['active'] = workspace.num

def init_knowledge():
    root = i3.get_tree()
    for workspace in root.workspaces():
        update_workspace(workspace)

last_update = 0

def update_state(i3, e):
    global last_update

    if not global_updates_running:
        return False
    if time.time() - last_update < 0.1:
        return False
    last_update = time.time()

    root = i3.get_tree()
    window = root.find_focused()
    current_workspace = window.workspace()

    # remove leftover desktops
    i3_active_wss = root.workspaces()
    deleted = []
    for num in global_knowledge["wss"].keys():
        if num not in [w.num for w in i3_active_wss]:
            deleted.append(num)
    deleted.sort() # make sure we're deleting the right items while iterating
    deleted.reverse()
    for num in deleted:
        del(global_knowledge["wss"][num])

    workspace_width = current_workspace.rect.width
    workspace_height = current_workspace.rect.height
    workspace_x = current_workspace.rect.x
    workspace_y = current_workspace.rect.y

    screenshot = grab_screen(x=workspace_x, y=workspace_y, w=workspace_width, h=workspace_height)

    update_workspace(current_workspace, screenshot)
    #time.sleep(0.5)


def get_hovered_frame(mpos, frames):
    for frame in frames.keys():
        if mpos[0] > frames[frame]['ul'][0] \
                and mpos[0] < frames[frame]['br'][0] \
                and mpos[1] > frames[frame]['ul'][1] \
                and mpos[1] < frames[frame]['br'][1]:
            return frame
    return None

def show_ui():
    global global_updates_running
    import math

    window_width = get_config('UI', 'window_width')
    window_height = get_config('UI', 'window_height')
    
    # workspaces = get_config('UI', 'workspaces')
    workspaces = len(global_knowledge["wss"])

    # tot_wss_w = sum(w["size"][0] for w in global_knowledge["wss"].values())
    # tot_wss_h = sum(w["size"][1] for w in global_knowledge["wss"].values())
    # print("tot_wss_w:", tot_wss_w, "tot_wss_h:", tot_wss_h)

    grid_x = get_config('UI', 'grid_x')
    grid_y = get_config('UI', 'grid_y')
    grid_x = grid_y = math.ceil(math.sqrt(workspaces))
    
    padding_x = get_config('UI', 'padding_percent_x')
    padding_y = get_config('UI', 'padding_percent_y')
    spacing_x = get_config('UI', 'spacing_percent_x')
    spacing_y = get_config('UI', 'spacing_percent_y')
    frame_width = get_config('UI', 'frame_width_px')
    
    frame_active_color = get_config('UI', 'frame_active_color')
    frame_inactive_color = get_config('UI', 'frame_inactive_color')
    frame_unknown_color = get_config('UI', 'frame_unknown_color')
    frame_empty_color = get_config('UI', 'frame_empty_color')
    frame_nonexistant_color = get_config('UI', 'frame_nonexistant_color')
    
    tile_active_color = get_config('UI', 'tile_active_color')
    tile_inactive_color = get_config('UI', 'tile_inactive_color')
    tile_unknown_color = get_config('UI', 'tile_unknown_color')
    tile_empty_color = get_config('UI', 'tile_empty_color')
    tile_nonexistant_color = get_config('UI', 'tile_nonexistant_color')
    
    names_show = get_config('UI', 'names_show')
    names_font = get_config('UI', 'names_font')
    names_fontsize = get_config('UI', 'names_fontsize')
    names_color = get_config('UI', 'names_color')

    thumb_stretch = get_config('UI', 'thumb_stretch')
    highlight_percentage = get_config('UI', 'highlight_percentage')

    switch_to_empty_workspaces = get_config('UI', 'switch_to_empty_workspaces')

    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    pygame.display.set_caption('i3expo-ng')

    total_x = screen.get_width()
    total_y = screen.get_height()

    pad_x = round(total_x * padding_x / 100)
    pad_y = round(total_y * padding_y / 100)
    # print("pad_x:", pad_x, "pad_y:", pad_y)

    space_x = round(total_x * spacing_x / 100)
    space_y = round(total_y * spacing_y / 100)
    # print("space_x:", space_x, "space_y:", space_y)

    shot_outer_x = round((total_x - 2 * pad_x - space_x * (grid_x - 1)) / grid_x)
    shot_outer_y = round((total_y - 2 * pad_y - space_y * (grid_y - 1)) / grid_y)

    shot_inner_x = shot_outer_x - 2 * frame_width 
    shot_inner_y = shot_outer_y - 2 * frame_width

    offset_delta_x = shot_outer_x + space_x
    offset_delta_y = shot_outer_y + space_y

    screen.fill(get_config('UI', 'bgcolor'))
    
    missing = pygame.Surface((150,200), pygame.SRCALPHA, 32) 
    missing = missing.convert_alpha()
    qm = pygame.font.SysFont('sans-serif', 150).render('?', True, (150, 150, 150))
    qm_size = qm.get_rect().size
    origin_x = round((150 - qm_size[0])/2)
    origin_y = round((200 - qm_size[1])/2)
    missing.blit(qm, (origin_x, origin_y))

    frames = {}

    font = pygame.font.SysFont(names_font, names_fontsize)

    wss_idx = [int(k) for k in global_knowledge["wss"].keys()]
    wsi = 0

    for y in range(grid_y):
        for x in range(grid_x):
            if wsi >= len(wss_idx):
                break
            # index = y * grid_x + x + 1
            index = wss_idx[min(wsi, len(wss_idx)-1)]
            wsi += 1

            frames[index] = {
                    'active': False,
                    'mouseoff': None,
                    'mouseon': None,
                    'ul': (None, None),
                    'br': (None, None)
            }

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
                image = missing
            elif index <= workspaces:
                tile_color = tile_empty_color
                frame_color = frame_empty_color
                image = None
            else:
                tile_color = tile_nonexistant_color
                frame_color = frame_nonexistant_color
                image = None

            origin_x = pad_x + offset_delta_x * x
            origin_y = pad_y + offset_delta_y * y

            frames[index]['ul'] = (origin_x, origin_y)
            frames[index]['br'] = (origin_x + shot_outer_x, origin_y + shot_outer_y)

            screen.fill(frame_color,
                    (
                        origin_x,
                        origin_y,
                        shot_outer_x,
                        shot_outer_y,
                    ))

            screen.fill(tile_color,
                    (
                        origin_x + frame_width,
                        origin_y + frame_width,
                        shot_inner_x,
                        shot_inner_y,
                    ))

            if image:
                if thumb_stretch:
                    image = pygame.transform.smoothscale(image, (shot_inner_x, shot_inner_y))
                    offset_x = 0
                    offset_y = 0
                else:
                    image_size = image.get_rect().size
                    image_x = image_size[0]
                    image_y = image_size[1]
                    ratio_x = shot_inner_x / image_x
                    ratio_y = shot_inner_y / image_y
                    if ratio_x < ratio_y:
                        result_x = shot_inner_x
                        result_y = round(ratio_x * image_y)
                        offset_x = 0
                        offset_y = round((shot_inner_y - result_y) / 2)
                    else:
                        result_x = round(ratio_y * image_x)
                        result_y = shot_inner_y
                        offset_x = round((shot_inner_x - result_x) / 2)
                        offset_y = 0
                    image = pygame.transform.smoothscale(image, (result_x, result_y))
                screen.blit(image, (origin_x + frame_width + offset_x, origin_y + frame_width + offset_y))

            mouseoff = screen.subsurface((origin_x, origin_y, shot_outer_x, shot_outer_y)).copy()
            lightmask = pygame.Surface((shot_outer_x, shot_outer_y), pygame.SRCALPHA, 32)
            lightmask.convert_alpha()
            lightmask.fill((255,255,255,255 * highlight_percentage / 100))
            mouseon = mouseoff.copy()
            mouseon.blit(lightmask, (0, 0))

            frames[index]['mouseon'] = mouseon.copy()
            frames[index]['mouseoff'] = mouseoff.copy()

            defined_name = False
            try:
                defined_name = config.get('Workspaces', 'workspace_' + str(index))
            except:
                pass

            if names_show and (index in global_knowledge["wss"].keys() or defined_name):
                if not defined_name:
                    name = global_knowledge["wss"][index]['name']
                else:
                    name = defined_name
                name = font.render(name, True, names_color)
                name_width = name.get_rect().size[0]
                name_x = origin_x + round((shot_outer_x - name_width) / 2)
                name_y = origin_y + shot_outer_y + round(shot_outer_y * 0.02)
                screen.blit(name, (name_x, name_y))

    pygame.display.flip()

    running = True
    use_mouse = True

    active_frame = None
    last_active_frame = 1

    while running and not global_updates_running and pygame.display.get_init():
        jump = False
        kbdmove = (0, 0)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEMOTION:
                use_mouse = True
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
                    jump = True
                pygame.event.clear()
                break


        if use_mouse:
            mpos = pygame.mouse.get_pos()
            af = get_hovered_frame(mpos, frames)
            active_frame = af if af is not None else last_active_frame
            last_active_frame = active_frame
        elif kbdmove != (0, 0):
            if active_frame == None:
                active_frame = 1
            if kbdmove[0] != 0:
                active_frame += kbdmove[0]
            elif kbdmove[1] != 0:
                active_frame += kbdmove[1] * grid_x
            if active_frame > workspaces:
                active_frame -= workspaces
            elif active_frame < 0:
                active_frame += workspaces
            print(active_frame)


        if jump:
            if active_frame in global_knowledge["wss"].keys():
                i3.command('workspace ' + str(global_knowledge["wss"][active_frame]['name']))
                break
            if switch_to_empty_workspaces:
                defined_name = False
                try:
                    defined_name = config.get('Workspaces', 'workspace_' + str(active_frame))
                except:
                    pass
                if defined_name:
                    i3.command('workspace ' + defined_name)
                    break

        for frame in frames.keys():
            if frames[frame]['active'] and not frame == active_frame:
                screen.blit(frames[frame]['mouseoff'], frames[frame]['ul'])
                frames[frame]['active'] = False
        if active_frame and not frames[active_frame]['active']:
            screen.blit(frames[active_frame]['mouseon'], frames[active_frame]['ul'])
            frames[active_frame]['active'] = True

        pygame.display.update()
        pygame.time.wait(25)

    pygame.display.quit()
    pygame.display.init()
    global_updates_running = True

if __name__ == '__main__':

    read_config()
    init_knowledge()
    update_state(i3, None)

    i3.on('window::new', update_state)
    i3.on('window::close', update_state)
    i3.on('window::move', update_state)
    i3.on('window::floating', update_state)
    i3.on('window::fullscreen_mode', update_state)
    #i3.on('workspace', update_state)

    i3_thread = Thread(target = i3.main)
    i3_thread.daemon = True
    i3_thread.start()

    while True:
        time.sleep(1)
        update_state(i3, None)
