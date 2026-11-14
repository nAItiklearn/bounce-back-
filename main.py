import math
import random
from pathlib import Path

import pygame

WINDOW_WIDTH = 1152
WINDOW_HEIGHT = 648
GAME_FPS = 60
LEVEL_WIDTH = 4224
GROUND_TOP = 584
TILE_PX = 64

HERO_WIDTH = 36
HERO_HEIGHT = 62
HERO_SPEED = 230
HERO_ACCEL = 1500
GRAVITY = 1500
HERO_JUMP = -680
HERO_SHOT_DELAY = 0.22
DYING_TIME = 1.1
COMEBACK_SHIELD_TIME = 3.0
FRIEND_HEAD_SIZE = 44
RESPAWN_SPOTS = [90, 1200, 2240, 3200]

WHITE = (239, 244, 228)
DARK = (24, 35, 43)
DARK_BLUE = (35, 52, 61)
BORDER = (108, 139, 137)
YELLOW = (255, 220, 92)
ORANGE = (245, 133, 66)
RED = (220, 74, 74)
CYAN = (104, 231, 223)

BASE_FOLDER = Path(__file__).resolve().parent
game_window = None
text_fonts = {}
game_art = {}
menu_hitboxes = {}


def make_missing_art(art_size=(28, 36)):
    missing_art = pygame.Surface(art_size, pygame.SRCALPHA)
    missing_art.fill((190, 75, 160))
    pygame.draw.rect(missing_art, WHITE, missing_art.get_rect(), 2)
    return missing_art


def load_picture(relative_path, picture_scale=1):
    full_path = BASE_FOLDER / relative_path
    try:
        picture = pygame.image.load(str(full_path))
        if picture.get_alpha() is not None:
            picture = picture.convert_alpha()
        else:
            picture = picture.convert()
    except (FileNotFoundError, pygame.error) as load_error:
        print(f"Warning: could not load {full_path}: {load_error}")
        if "downs_" in str(relative_path):
            picture = make_missing_art((384, 216))
        else:
            picture = make_missing_art()

    picture_width = int(picture.get_width() * picture_scale)
    picture_height = int(picture.get_height() * picture_scale)
    return pygame.transform.scale(picture, (picture_width, picture_height))


def load_moves(move_folder, picture_scale=2):
    full_folder = BASE_FOLDER / move_folder
    frame_paths = list(full_folder.glob("*.png"))
    frame_paths.sort(key=lambda frame_path: int(frame_path.stem))
    move_frames = []
    for frame_path in frame_paths:
        relative_path = frame_path.relative_to(BASE_FOLDER)
        move_frames.append(load_picture(relative_path, picture_scale))
    if not move_frames:
        print(f"Warning: no pictures found in {full_folder}")
        move_frames.append(make_missing_art((56, 72)))
    return move_frames


def load_friend_heads():
    friend_heads = []
    picture_paths = sorted(
        path for path in BASE_FOLDER.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    for picture_path in picture_paths:
        try:
            picture = pygame.image.load(str(picture_path)).convert_alpha()
        except (FileNotFoundError, pygame.error) as load_error:
            print(f"Warning: could not load {picture_path}: {load_error}")
            continue

        head = pygame.transform.smoothscale(
            picture, (FRIEND_HEAD_SIZE, FRIEND_HEAD_SIZE)
        )

        for pixel_x in range(FRIEND_HEAD_SIZE):
            for pixel_y in range(FRIEND_HEAD_SIZE):
                colour = head.get_at((pixel_x, pixel_y))
                if colour.r > colour.g * 1.35 and colour.r > colour.b * 1.8:
                    colour.a = 0
                    head.set_at((pixel_x, pixel_y), colour)

        circle_mask = pygame.Surface(head.get_size(), pygame.SRCALPHA)
        centre = FRIEND_HEAD_SIZE // 2
        pygame.draw.circle(circle_mask, WHITE, (centre, centre), centre - 1)
        head.blit(circle_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.circle(head, WHITE, (centre, centre), centre - 1, 1)
        friend_heads.append(head)

    if not friend_heads:
        print("Warning: no friend headshots found in the game folder")
    return friend_heads


def load_noise(relative_path):
    if not pygame.mixer.get_init():
        return None
    try:
        return pygame.mixer.Sound(str(BASE_FOLDER / relative_path))
    except (FileNotFoundError, pygame.error) as load_error:
        print(f"Warning: could not load {relative_path}: {load_error}")
        return None


def play_noise(noise_name, loudness):
    noise = game_art["noises"].get(noise_name)
    if noise is not None:
        noise.set_volume(loudness)
        noise.play()


def load_game_art():
    game_art["backdrops"] = []
    backdrop_names = ["0_sky", "1_far", "2_mid", "3_near"]
    for backdrop_name in backdrop_names:
        picture_path = Path("vista-ten/downs") / f"downs_{backdrop_name}.png"
        game_art["backdrops"].append(load_picture(picture_path, 3))

    game_art["hero"] = {}
    game_art["guard"] = {}
    for move_name in ["Idle", "Run", "Death"]:
        game_art["hero"][move_name] = load_moves(Path("img/player") / move_name)
        game_art["guard"][move_name] = load_moves(Path("img/enemy") / move_name)
    game_art["hero"]["Jump"] = load_moves(Path("img/player/Jump"))
    game_art["friend_heads"] = load_friend_heads()

    game_art["ground"] = load_picture(Path("img/tile/7.png"), 2)
    game_art["platform"] = load_picture(Path("img/tile/8.png"), 2)
    game_art["noises"] = {
        "shot": load_noise(Path("audio/shot.wav")),
        "jump": load_noise(Path("audio/jump.wav")),
        "defeat": load_noise(Path("audio/grenade.wav")),
    }


def make_platforms():
    platform_layout = [
        (768, 456, 4),
        (1152, 424, 5),
        (1664, 488, 3),
        (1984, 392, 5),
        (2432, 456, 4),
        (2816, 424, 4),
    ]
    platform_boxes = []
    for left, top, tile_count in platform_layout:
        platform_box = pygame.Rect(left, top, tile_count * TILE_PX, TILE_PX)
        platform_boxes.append(platform_box)
    return platform_boxes


def make_guard(start_x, top, patrol_left, patrol_right, first_shot_delay):
    return {
        "x": float(start_x),
        "y": float(top),
        "health": 3,
        "way": -1,
        "patrol_left": patrol_left,
        "patrol_right": patrol_right,
        "shot_wait": first_shot_delay,
        "flash_time": 0.0,
        "animation_time": 0.0,
        "sees_hero": False,
    }


def make_guards():
    guards = [
        make_guard(700, GROUND_TOP - HERO_HEIGHT, 640, 790, 1.0),
        make_guard(1330, 424 - HERO_HEIGHT, 1280, 1410, 1.5),
        make_guard(2400, GROUND_TOP - HERO_HEIGHT, 2340, 2530, 1.2),
        make_guard(3750, GROUND_TOP - HERO_HEIGHT, 3650, 3950, 0.8),
    ]
    return guards


def make_hero():
    return {
        "x": 90.0,
        "y": float(GROUND_TOP - HERO_HEIGHT),
        "speed_x": 0.0,
        "speed_y": 0.0,
        "facing": 1,
        "on_ground": True,
        "animation_time": 0.0,
        "shot_wait": 0.0,
        "hits": 0,
        "head_index": -1,
        "dying": False,
        "death_time": 0.0,
        "shield_time": 0.0,
        "message_time": 0.0,
        "respawn_x": 90.0,
    }


def make_round():
    return {
        "hero": make_hero(),
        "guards": make_guards(),
        "platforms": make_platforms(),
        "hero_shots": [],
        "guard_shots": [],
        "sparks": [],
        "guard_deaths": [],
        "new_guard_wait": 2.0,
        "score": 0,
        "camera_x": 0.0,
        "shake_time": 0.0,
        "jump_now": False,
        "play_time": 0.0,
    }


def hero_body(hero):
    return pygame.Rect(round(hero["x"]), round(hero["y"]), HERO_WIDTH, HERO_HEIGHT)


def guard_body(guard):
    return pygame.Rect(round(guard["x"]), round(guard["y"]), HERO_WIDTH, HERO_HEIGHT)


def change_speed(speed_now, wanted_speed, speed_change):
    if speed_now < wanted_speed:
        return min(speed_now + speed_change, wanted_speed)
    return max(speed_now - speed_change, wanted_speed)


def level_walls(round_data):
    ground_box = pygame.Rect(0, GROUND_TOP, LEVEL_WIDTH, WINDOW_HEIGHT - GROUND_TOP)
    return round_data["platforms"] + [ground_box]


def loop_level(round_data):
    round_data["guards"] = make_guards()
    round_data["hero_shots"].clear()
    round_data["guard_shots"].clear()
    round_data["sparks"].clear()
    round_data["guard_deaths"].clear()
    round_data["new_guard_wait"] = 2.0


def move_hero(round_data, delta_time, move_way):
    hero = round_data["hero"]
    wanted_speed = move_way * HERO_SPEED
    speed_change = HERO_ACCEL * delta_time
    hero["speed_x"] = change_speed(hero["speed_x"], wanted_speed, speed_change)
    if move_way != 0:
        hero["facing"] = move_way

    if round_data["jump_now"] and hero["on_ground"]:
        hero["speed_y"] = HERO_JUMP
        hero["on_ground"] = False
        play_noise("jump", 0.3)
    round_data["jump_now"] = False

    hero["x"] += hero["speed_x"] * delta_time
    if hero["x"] > LEVEL_WIDTH - HERO_WIDTH:
        hero["x"] = 0.0
        round_data["camera_x"] = 0.0
        loop_level(round_data)
    elif hero["x"] < 0:
        hero["x"] = float(LEVEL_WIDTH - HERO_WIDTH)
        round_data["camera_x"] = float(LEVEL_WIDTH - WINDOW_WIDTH)
        loop_level(round_data)

    old_feet = hero["y"] + HERO_HEIGHT
    hero["speed_y"] += GRAVITY * delta_time
    hero["y"] += hero["speed_y"] * delta_time
    new_feet = hero["y"] + HERO_HEIGHT
    hero["on_ground"] = False

    if hero["speed_y"] >= 0:
        landing_top = None
        body = hero_body(hero)
        for wall_box in level_walls(round_data):
            crossed_top = old_feet <= wall_box.top + 2 and new_feet >= wall_box.top
            inside_sides = body.right > wall_box.left and body.left < wall_box.right
            if crossed_top and inside_sides:
                if landing_top is None or wall_box.top < landing_top:
                    landing_top = wall_box.top
        if landing_top is not None:
            hero["y"] = landing_top - HERO_HEIGHT
            hero["speed_y"] = 0.0
            hero["on_ground"] = True

    hero["animation_time"] += delta_time
    if hero["on_ground"]:
        for respawn_x in RESPAWN_SPOTS:
            if hero["x"] >= respawn_x:
                hero["respawn_x"] = max(hero["respawn_x"], respawn_x)


def make_sparks(round_data, spark_x, spark_y, spark_colour, spark_count):
    for spark_number in range(spark_count):
        round_data["sparks"].append({
            "x": spark_x,
            "y": spark_y,
            "speed_x": random.uniform(-120, 120),
            "speed_y": random.uniform(-170, 30),
            "life": random.uniform(0.18, 0.45),
            "colour": spark_colour,
            "size": random.choice([3, 4, 6]),
        })


def shoot_hero(round_data):
    hero = round_data["hero"]
    if hero["shot_wait"] > 0 or hero["dying"]:
        return

    shot_way = hero["facing"]
    hero_shot = {
        "x": hero["x"] + HERO_WIDTH / 2 + shot_way * 25,
        "y": hero["y"] + 25,
        "speed_x": shot_way * 700,
        "speed_y": 0,
        "radius": 5,
    }
    round_data["hero_shots"].append(hero_shot)
    hero["shot_wait"] = HERO_SHOT_DELAY
    play_noise("shot", 0.16)
    make_sparks(round_data, hero_shot["x"], hero_shot["y"], YELLOW, 3)


def shot_body(shot):
    shot_radius = shot["radius"]
    shot_left = round(shot["x"] - shot_radius)
    shot_top = round(shot["y"] - shot_radius)
    return pygame.Rect(shot_left, shot_top, shot_radius * 2, shot_radius * 2)


def shot_offscreen(round_data, shot):
    camera_x = round_data["camera_x"]
    outside_left = shot["x"] < camera_x - 50
    outside_right = shot["x"] > camera_x + WINDOW_WIDTH + 50
    outside_top = shot["y"] < -50
    outside_bottom = shot["y"] > WINDOW_HEIGHT + 50
    return outside_left or outside_right or outside_top or outside_bottom


def shot_hits_wall(round_data, shot):
    for wall_box in level_walls(round_data):
        if shot_body(shot).colliderect(wall_box):
            return True
    return False


def defeat_guard(round_data, guard):
    round_data["score"] += 100
    round_data["guard_deaths"].append({
        "x": guard["x"],
        "y": guard["y"],
        "way": guard["way"],
        "time": 0.0,
        "duration": 0.8,
    })
    make_sparks(round_data, guard["x"] + 18, guard["y"] + 30, YELLOW, 16)
    round_data["guards"].remove(guard)
    play_noise("defeat", 0.12)


def move_hero_shots(round_data, delta_time):
    for hero_shot in round_data["hero_shots"][:]:
        hero_shot["x"] += hero_shot["speed_x"] * delta_time
        hero_shot["y"] += hero_shot["speed_y"] * delta_time

        if shot_offscreen(round_data, hero_shot) or shot_hits_wall(round_data, hero_shot):
            round_data["hero_shots"].remove(hero_shot)
            continue

        for guard in round_data["guards"][:]:
            if shot_body(hero_shot).colliderect(guard_body(guard)):
                round_data["hero_shots"].remove(hero_shot)
                guard["health"] -= 1
                make_sparks(round_data, hero_shot["x"], hero_shot["y"], ORANGE, 7)
                if guard["health"] <= 0:
                    defeat_guard(round_data, guard)
                break


def guard_can_see_hero(round_data, guard):
    hero = round_data["hero"]
    guard_centre = guard_body(guard).center
    hero_centre = hero_body(hero).center
    for wall_box in level_walls(round_data):
        if wall_box.clipline(guard_centre, hero_centre):
            return False
    return True


def shoot_guard(round_data, guard):
    hero = round_data["hero"]
    muzzle_x = guard["x"] + HERO_WIDTH / 2 + guard["way"] * 24
    muzzle_y = guard["y"] + 25
    aim_x = hero["x"] + HERO_WIDTH / 2
    aim_y = hero["y"] + HERO_HEIGHT / 2
    aim_distance_x = aim_x - muzzle_x
    aim_distance_y = aim_y - muzzle_y
    aim_distance = math.hypot(aim_distance_x, aim_distance_y)
    if aim_distance == 0:
        return

    guard_shot_speed = 330
    round_data["guard_shots"].append({
        "x": muzzle_x,
        "y": muzzle_y,
        "speed_x": aim_distance_x / aim_distance * guard_shot_speed,
        "speed_y": aim_distance_y / aim_distance * guard_shot_speed,
        "radius": 6,
    })
    guard["flash_time"] = 0.12
    make_sparks(round_data, muzzle_x, muzzle_y, ORANGE, 4)


def update_guards(round_data, delta_time):
    hero = round_data["hero"]
    hero_hitbox = hero_body(hero)

    for guard in round_data["guards"]:
        guard["animation_time"] += delta_time
        guard["shot_wait"] -= delta_time
        guard["flash_time"] = max(0, guard["flash_time"] - delta_time)

        guard_hitbox = guard_body(guard)
        distance_x = hero_hitbox.centerx - guard_hitbox.centerx
        distance_y = hero_hitbox.centery - guard_hitbox.centery
        hero_distance = math.hypot(distance_x, distance_y)
        hero_in_range = hero_distance <= 460
        hero_visible = hero_in_range and guard_can_see_hero(round_data, guard)
        guard["sees_hero"] = hero_visible

        if hero_visible:
            guard["way"] = 1 if distance_x >= 0 else -1
            if guard["shot_wait"] <= 0:
                shoot_guard(round_data, guard)
                guard["shot_wait"] = 1.8
        else:
            guard["x"] += guard["way"] * 42 * delta_time
            if guard["x"] <= guard["patrol_left"]:
                guard["x"] = float(guard["patrol_left"])
                guard["way"] = 1
            elif guard["x"] >= guard["patrol_right"]:
                guard["x"] = float(guard["patrol_right"])
                guard["way"] = -1


def hurt_hero(round_data):
    hero = round_data["hero"]
    if hero["dying"] or hero["shield_time"] > 0:
        return False

    hero["hits"] += 1
    friend_heads = game_art.get("friend_heads", [])
    if friend_heads:
        new_head = random.randrange(len(friend_heads))
        if new_head == hero["head_index"]:
            new_head = (new_head + 1) % len(friend_heads)
        hero["head_index"] = new_head

    hero["dying"] = True
    hero["death_time"] = 0.0
    hero["speed_x"] = 0.0
    hero["speed_y"] = 0.0
    hero["shield_time"] = 0.0
    hero["message_time"] = 0.0
    round_data["score"] = max(0, round_data["score"] - 50)
    round_data["shake_time"] = 0.35
    round_data["guard_shots"].clear()
    make_sparks(round_data, hero["x"] + 18, hero["y"] + 30, RED, 14)
    return True


def move_guard_shots(round_data, delta_time):
    for guard_shot in round_data["guard_shots"][:]:
        guard_shot["x"] += guard_shot["speed_x"] * delta_time
        guard_shot["y"] += guard_shot["speed_y"] * delta_time

        if shot_offscreen(round_data, guard_shot) or shot_hits_wall(round_data, guard_shot):
            round_data["guard_shots"].remove(guard_shot)
            continue

        if shot_body(guard_shot).colliderect(hero_body(round_data["hero"])):
            hurt_hero(round_data)
            break


def bring_hero_back(round_data):
    hero = round_data["hero"]
    hero["x"] = hero["respawn_x"]
    hero["y"] = float(GROUND_TOP - HERO_HEIGHT)
    hero["speed_x"] = 0.0
    hero["speed_y"] = 0.0
    hero["on_ground"] = True
    hero["dying"] = False
    hero["death_time"] = 0.0
    hero["shield_time"] = COMEBACK_SHIELD_TIME
    hero["message_time"] = 2.3
    hero["shot_wait"] = 0.25
    hero["animation_time"] = 0.0
    round_data["guard_shots"].clear()


def update_hero_death(round_data, delta_time):
    hero = round_data["hero"]
    hero["death_time"] += delta_time
    if hero["death_time"] < DYING_TIME:
        return None
    bring_hero_back(round_data)
    return None


def update_sparks(round_data, delta_time):
    for spark in round_data["sparks"][:]:
        spark["life"] -= delta_time
        if spark["life"] <= 0:
            round_data["sparks"].remove(spark)
            continue
        spark["speed_y"] += 500 * delta_time
        spark["x"] += spark["speed_x"] * delta_time
        spark["y"] += spark["speed_y"] * delta_time

    for guard_death in round_data["guard_deaths"][:]:
        guard_death["time"] += delta_time
        if guard_death["time"] >= guard_death["duration"]:
            round_data["guard_deaths"].remove(guard_death)


def update_camera(round_data, delta_time):
    hero = round_data["hero"]
    wanted_camera_x = hero["x"] - WINDOW_WIDTH * 0.38
    wanted_camera_x = max(0, min(wanted_camera_x, LEVEL_WIDTH - WINDOW_WIDTH))
    camera_change = (wanted_camera_x - round_data["camera_x"]) * min(1, delta_time * 6)
    round_data["camera_x"] += camera_change


def update_round(round_data, delta_time, move_way=0, firing=False):
    hero = round_data["hero"]
    round_data["shake_time"] = max(0, round_data["shake_time"] - delta_time)

    if hero["dying"]:
        update_sparks(round_data, delta_time)
        return update_hero_death(round_data, delta_time)

    round_data["play_time"] += delta_time
    hero["shot_wait"] = max(0, hero["shot_wait"] - delta_time)
    hero["shield_time"] = max(0, hero["shield_time"] - delta_time)
    hero["message_time"] = max(0, hero["message_time"] - delta_time)

    move_hero(round_data, delta_time, move_way)
    if firing:
        shoot_hero(round_data)
    move_hero_shots(round_data, delta_time)

    if not round_data["guards"]:
        round_data["new_guard_wait"] -= delta_time
        if round_data["new_guard_wait"] <= 0:
            round_data["guards"] = make_guards()
            round_data["new_guard_wait"] = 2.0
    else:
        round_data["new_guard_wait"] = 2.0

    update_guards(round_data, delta_time)
    move_guard_shots(round_data, delta_time)

    if not hero["dying"]:
        for guard in round_data["guards"]:
            if hero_body(hero).colliderect(guard_body(guard)):
                hurt_hero(round_data)
                break

    if hero["y"] > WINDOW_HEIGHT + 100:
        hurt_hero(round_data)

    update_sparks(round_data, delta_time)
    update_camera(round_data, delta_time)
    return None


def draw_background(window, camera_x):
    scroll_speeds = [0.0, 0.2, 0.4, 0.8]
    for layer_number in range(4):
        backdrop = game_art["backdrops"][layer_number]
        scroll_speed = scroll_speeds[layer_number]
        backdrop_width = backdrop.get_width()
        backdrop_x = -(int(camera_x * scroll_speed) % backdrop_width)
        window.blit(backdrop, (backdrop_x, 0))
        window.blit(backdrop, (backdrop_x + backdrop_width, 0))


def draw_level_tiles(window, round_data, camera_x, shake_x, shake_y):
    first_tile = int(camera_x // TILE_PX) - 1
    last_tile = first_tile + WINDOW_WIDTH // TILE_PX + 3
    for tile_number in range(first_tile, last_tile):
        tile_world_x = tile_number * TILE_PX
        if 0 <= tile_world_x < LEVEL_WIDTH:
            tile_screen_x = round(tile_world_x - camera_x + shake_x)
            window.blit(game_art["ground"], (tile_screen_x, GROUND_TOP + shake_y))

    for platform_box in round_data["platforms"]:
        tile_range = range(platform_box.left, platform_box.right, TILE_PX)
        for tile_world_x in tile_range:
            tile_screen_x = round(tile_world_x - camera_x + shake_x)
            if -TILE_PX <= tile_screen_x <= WINDOW_WIDTH:
                tile_position = (tile_screen_x, platform_box.top + shake_y)
                window.blit(game_art["platform"], tile_position)


def draw_hero(window, round_data, camera_x, shake_x, shake_y):
    hero = round_data["hero"]
    if hero["dying"]:
        hero_frames = game_art["hero"]["Death"]
        frame_number = int(hero["death_time"] / DYING_TIME * len(hero_frames))
        frame_number = min(frame_number, len(hero_frames) - 1)
    elif not hero["on_ground"]:
        hero_frames = game_art["hero"]["Jump"]
        frame_number = 0
    elif abs(hero["speed_x"]) > 20:
        hero_frames = game_art["hero"]["Run"]
        frame_number = int(hero["animation_time"] * 12) % len(hero_frames)
    else:
        hero_frames = game_art["hero"]["Idle"]
        frame_number = int(hero["animation_time"] * 7) % len(hero_frames)

    hero_picture = hero_frames[frame_number]
    hero_picture = pygame.transform.flip(hero_picture, hero["facing"] < 0, False)
    blinking = hero["shield_time"] > 0 and int(hero["shield_time"] * 12) % 2 == 0
    if blinking:
        hero_picture = hero_picture.copy()
        hero_picture.set_alpha(115)

    hero_draw_x = round(hero["x"] + HERO_WIDTH / 2 - camera_x + shake_x)
    hero_draw_y = round(hero["y"] + HERO_HEIGHT + 5 + shake_y)
    picture_box = hero_picture.get_rect(midbottom=(hero_draw_x, hero_draw_y))
    window.blit(hero_picture, picture_box)

    friend_heads = game_art.get("friend_heads", [])
    if friend_heads and hero["head_index"] >= 0 and not hero["dying"]:
        friend_head = friend_heads[hero["head_index"]]
        head_box = friend_head.get_rect(center=(hero_draw_x, picture_box.top + 15))
        window.blit(friend_head, head_box)

    if hero["shield_time"] > 0 and not hero["dying"]:
        shield_centre = (hero_draw_x, round(hero["y"] + 31 + shake_y))
        pygame.draw.circle(window, CYAN, shield_centre, 45, 2)
        shield_box = (shield_centre[0] - 49, shield_centre[1] - 49, 98, 98)
        arc_start = round_data["play_time"] * 3
        pygame.draw.arc(window, WHITE, shield_box, arc_start, arc_start + 1.5, 3)


def draw_guards(window, round_data, camera_x, shake_x, shake_y):
    for guard in round_data["guards"]:
        if guard["sees_hero"]:
            guard_frames = game_art["guard"]["Idle"]
            frame_speed = 7
        else:
            guard_frames = game_art["guard"]["Run"]
            frame_speed = 9
        frame_number = int(guard["animation_time"] * frame_speed) % len(guard_frames)

        guard_picture = guard_frames[frame_number]
        guard_picture = pygame.transform.flip(guard_picture, guard["way"] > 0, False)
        guard_draw_x = round(guard["x"] + 18 - camera_x + shake_x)
        guard_draw_y = round(guard["y"] + HERO_HEIGHT + 5 + shake_y)
        picture_box = guard_picture.get_rect(midbottom=(guard_draw_x, guard_draw_y))
        if picture_box.right < -50 or picture_box.left > WINDOW_WIDTH + 50:
            continue

        window.blit(guard_picture, picture_box)
        if guard["health"] < 3:
            health_box = pygame.Rect(guard_draw_x - 20, picture_box.top - 9, 40, 5)
            pygame.draw.rect(window, DARK, health_box)
            health_width = round(40 * guard["health"] / 3)
            pygame.draw.rect(window, RED, (health_box.x, health_box.y, health_width, 5))

        if guard["flash_time"] > 0:
            flash_x = guard_draw_x + guard["way"] * 34
            flash_y = round(guard["y"] + 25 + shake_y)
            pygame.draw.rect(window, YELLOW, (flash_x - 5, flash_y - 5, 10, 10))


def draw_guard_deaths(window, round_data, camera_x, shake_x, shake_y):
    death_frames = game_art["guard"]["Death"]
    for guard_death in round_data["guard_deaths"]:
        frame_number = int(guard_death["time"] / guard_death["duration"] * len(death_frames))
        frame_number = min(frame_number, len(death_frames) - 1)
        death_picture = death_frames[frame_number]
        death_picture = pygame.transform.flip(death_picture, guard_death["way"] > 0, False)
        death_x = round(guard_death["x"] + 18 - camera_x + shake_x)
        death_y = round(guard_death["y"] + HERO_HEIGHT + 5 + shake_y)
        window.blit(death_picture, death_picture.get_rect(midbottom=(death_x, death_y)))


def draw_shots_and_sparks(window, round_data, camera_x, shake_x, shake_y):
    for hero_shot in round_data["hero_shots"]:
        shot_x = round(hero_shot["x"] - camera_x + shake_x)
        shot_y = round(hero_shot["y"] + shake_y)
        pygame.draw.rect(window, YELLOW, (shot_x - 7, shot_y - 3, 14, 6))
        pygame.draw.rect(window, WHITE, (shot_x - 2, shot_y - 2, 5, 4))

    for guard_shot in round_data["guard_shots"]:
        shot_x = round(guard_shot["x"] - camera_x + shake_x)
        shot_y = round(guard_shot["y"] + shake_y)
        pygame.draw.circle(window, DARK, (shot_x, shot_y), 8)
        pygame.draw.circle(window, ORANGE, (shot_x, shot_y), 6)
        pygame.draw.circle(window, YELLOW, (shot_x, shot_y), 2)

    for spark in round_data["sparks"]:
        spark_x = round(spark["x"] - camera_x + shake_x)
        spark_y = round(spark["y"] + shake_y)
        spark_size = spark["size"]
        pygame.draw.rect(window, spark["colour"], (spark_x, spark_y, spark_size, spark_size))


def draw_round(window, round_data):
    camera_x = round_data["camera_x"]
    draw_background(window, camera_x)
    shake_x = 0
    shake_y = 0
    if round_data["shake_time"] > 0:
        shake_power = max(2, int(9 * round_data["shake_time"] / 0.35))
        shake_x = random.randint(-shake_power, shake_power)
        shake_y = random.randint(-shake_power, shake_power)

    draw_level_tiles(window, round_data, camera_x, shake_x, shake_y)
    draw_guard_deaths(window, round_data, camera_x, shake_x, shake_y)
    draw_guards(window, round_data, camera_x, shake_x, shake_y)
    draw_hero(window, round_data, camera_x, shake_x, shake_y)
    draw_shots_and_sparks(window, round_data, camera_x, shake_x, shake_y)


def write_text(window, words, font_name, colour, text_position, centred=False, shadow=False):
    chosen_font = text_fonts[font_name]
    if shadow:
        shadow_picture = chosen_font.render(words, False, DARK)
        shadow_box = shadow_picture.get_rect()
        if centred:
            shadow_box.center = (text_position[0] + 3, text_position[1] + 3)
        else:
            shadow_box.topleft = (text_position[0] + 3, text_position[1] + 3)
        window.blit(shadow_picture, shadow_box)

    text_picture = chosen_font.render(words, False, colour)
    text_box = text_picture.get_rect()
    if centred:
        text_box.center = text_position
    else:
        text_box.topleft = text_position
    window.blit(text_picture, text_box)


def draw_heart(window, heart_x, heart_y, filled):
    heart_colour = RED if filled else (73, 74, 77)
    heart_points = [
        (heart_x + 3, heart_y), (heart_x + 10, heart_y),
        (heart_x + 14, heart_y + 4), (heart_x + 18, heart_y),
        (heart_x + 25, heart_y), (heart_x + 29, heart_y + 4),
        (heart_x + 29, heart_y + 13), (heart_x + 25, heart_y + 17),
        (heart_x + 14, heart_y + 28), (heart_x + 3, heart_y + 17),
        (heart_x, heart_y + 13), (heart_x, heart_y + 4),
    ]
    pygame.draw.polygon(window, heart_colour, heart_points)
    pygame.draw.lines(window, DARK, True, heart_points, 2)


def draw_hud(window, round_data):
    hud_box = pygame.Rect(16, 14, WINDOW_WIDTH - 32, 66)
    pygame.draw.rect(window, DARK, hud_box)
    pygame.draw.rect(window, BORDER, hud_box, 2)

    hero = round_data["hero"]
    hit_words = f"HITS  {hero['hits']:03d}"
    write_text(window, hit_words, "small", WHITE, (32, 30))
    friend_heads = game_art.get("friend_heads", [])
    if friend_heads and hero["head_index"] >= 0:
        head_preview = friend_heads[hero["head_index"]]
        window.blit(head_preview, (157, 30))
        write_text(window, f"FRIEND {hero['head_index'] + 1}", "tiny", YELLOW, (198, 37))
    else:
        write_text(window, "NO GAME OVER", "tiny", BORDER, (157, 37))

    if hero["shield_time"] > 0:
        shield_words = f"SHIELD  {hero['shield_time']:.1f}s"
        write_text(window, shield_words, "small", CYAN, (WINDOW_WIDTH // 2, 47), True)
    else:
        write_text(window, "SHIELD OFF", "tiny", BORDER, (WINDOW_WIDTH // 2, 47), True)

    score_words = f"SCORE  {round_data['score']:05d}"
    score_width = text_fonts["small"].size(score_words)[0]
    score_x = WINDOW_WIDTH - 34 - score_width
    write_text(window, score_words, "small", WHITE, (score_x, 28))
    guard_words = f"ENEMIES  {len(round_data['guards'])}"
    write_text(window, guard_words, "tiny", YELLOW, (score_x, 54))

    if hero["message_time"] > 0:
        comeback_words = "YOU'RE BACK. KEEP GOING!"
        words_width = text_fonts["small"].size(comeback_words)[0]
        message_box = pygame.Rect(0, 0, words_width + 34, 44)
        message_box.midtop = (WINDOW_WIDTH // 2, 94)
        pygame.draw.rect(window, DARK, message_box)
        pygame.draw.rect(window, CYAN, message_box, 2)
        write_text(window, comeback_words, "small", WHITE, message_box.center, True)

    if round_data["play_time"] < 8:
        controls = "A / D  MOVE    SPACE  JUMP    LEFT CLICK  FIRE    ESC  PAUSE"
        write_text(window, controls, "tiny", WHITE, (24, WINDOW_HEIGHT - 27), shadow=True)


def draw_menu_button(window, button_box, button_words, button_action):
    menu_hitboxes[button_action] = button_box
    hovered = button_box.collidepoint(pygame.mouse.get_pos())
    button_colour = (69, 96, 94) if hovered else DARK_BLUE
    border_colour = YELLOW if hovered else BORDER

    pygame.draw.rect(window, DARK, button_box.move(5, 5))
    pygame.draw.rect(window, button_colour, button_box)
    pygame.draw.rect(window, border_colour, button_box, 3)
    write_text(window, button_words, "button", WHITE, button_box.center, True)


def draw_menu_backdrop(window):
    moving_camera = pygame.time.get_ticks() * 0.006
    draw_background(window, moving_camera)
    for tile_x in range(0, WINDOW_WIDTH, TILE_PX):
        window.blit(game_art["ground"], (tile_x, GROUND_TOP))


def draw_start_screen(window):
    write_text(window, "BOUNCE BACK", "title", WHITE,
               (WINDOW_WIDTH // 2, 145), True, True)
    write_text(window, "ENDLESS MODE", "small", YELLOW,
               (WINDOW_WIDTH // 2, 218), True, True)
    draw_menu_button(window, pygame.Rect(436, 300, 280, 68), "PLAY", "play")
    draw_menu_button(window, pygame.Rect(436, 395, 280, 68), "QUIT", "quit")
    write_text(window, "A/D OR ARROWS - MOVE   SPACE - JUMP   MOUSE - FIRE",
               "tiny", WHITE, (WINDOW_WIDTH // 2, 532), True, True)
    write_text(window, "NO GAME OVER. EVERY HIT SWAPS YOUR HEAD.", "tiny", WHITE,
               (WINDOW_WIDTH // 2, 560), True, True)


def dim_screen(window):
    dim_layer = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    dim_layer.fill((15, 23, 29, 190))
    window.blit(dim_layer, (0, 0))


def draw_pause_screen(window):
    dim_screen(window)
    write_text(window, "PAUSED", "title", WHITE,
               (WINDOW_WIDTH // 2, 160), True, True)
    draw_menu_button(window, pygame.Rect(436, 260, 280, 62), "RESUME", "resume")
    draw_menu_button(window, pygame.Rect(436, 345, 280, 62), "RESTART", "restart")
    draw_menu_button(window, pygame.Rect(436, 430, 280, 62), "QUIT", "quit")


def draw_end_screen(window, round_data):
    dim_screen(window)
    write_text(window, "GAME OVER", "title", RED,
               (WINDOW_WIDTH // 2, 170), True, True)
    final_score = f"SCORE  {round_data['score']:05d}"
    write_text(window, final_score, "button", WHITE,
               (WINDOW_WIDTH // 2, 265), True, True)
    draw_menu_button(window, pygame.Rect(436, 345, 280, 62), "RESTART", "restart")
    draw_menu_button(window, pygame.Rect(436, 430, 280, 62), "MAIN MENU", "main_menu")


def draw_screen(window, screen_name, current_round):
    global menu_hitboxes
    menu_hitboxes = {}

    if screen_name == "menu" or current_round is None:
        draw_menu_backdrop(window)
    else:
        draw_round(window, current_round)
        draw_hud(window, current_round)

    if screen_name == "menu":
        draw_start_screen(window)
    elif screen_name == "paused":
        draw_pause_screen(window)
    elif screen_name == "game_over":
        draw_end_screen(window, current_round)


def menu_choice(mouse_position):
    for button_action, button_box in menu_hitboxes.items():
        if button_box.collidepoint(mouse_position):
            return button_action
    return None


def main():
    global game_window, text_fonts

    pygame.init()
    game_window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("BOUNCE BACK")
    text_fonts = {
        "title": pygame.font.Font(None, 92),
        "button": pygame.font.Font(None, 42),
        "small": pygame.font.Font(None, 30),
        "tiny": pygame.font.Font(None, 23),
    }
    load_game_art()

    try:
        pygame.mixer.music.load(str(BASE_FOLDER / "audio/music2.mp3"))
        pygame.mixer.music.set_volume(0.22)
        pygame.mixer.music.play(-1)
    except (FileNotFoundError, pygame.error) as music_error:
        print(f"Warning: music could not play: {music_error}")

    game_clock = pygame.time.Clock()
    screen_name = "menu"
    current_round = None
    game_running = True

    while game_running:
        delta_time = min(game_clock.tick(GAME_FPS) / 1000.0, 0.05)

        for game_event in pygame.event.get():
            if game_event.type == pygame.QUIT:
                game_running = False

            if game_event.type == pygame.KEYDOWN:
                if game_event.key == pygame.K_ESCAPE:
                    if screen_name == "playing":
                        screen_name = "paused"
                    elif screen_name == "paused":
                        screen_name = "playing"
                if game_event.key == pygame.K_SPACE and screen_name == "playing":
                    current_round["jump_now"] = True
                if game_event.key == pygame.K_RETURN and screen_name == "menu":
                    current_round = make_round()
                    screen_name = "playing"

            if game_event.type == pygame.MOUSEBUTTONDOWN and game_event.button == 1:
                chosen_action = menu_choice(game_event.pos)
                if chosen_action in ["play", "restart"]:
                    current_round = make_round()
                    screen_name = "playing"
                elif chosen_action == "resume":
                    screen_name = "playing"
                elif chosen_action == "main_menu":
                    current_round = None
                    screen_name = "menu"
                elif chosen_action == "quit":
                    game_running = False

        if screen_name == "playing":
            pressed_keys = pygame.key.get_pressed()
            move_way = 0
            if pressed_keys[pygame.K_a] or pressed_keys[pygame.K_LEFT]:
                move_way -= 1
            if pressed_keys[pygame.K_d] or pressed_keys[pygame.K_RIGHT]:
                move_way += 1
            firing = pygame.mouse.get_pressed()[0]
            round_result = update_round(current_round, delta_time, move_way, firing)
            if round_result is not None:
                screen_name = round_result

        draw_screen(game_window, screen_name, current_round)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
