import arcade
import numpy as np
from typing import Optional
import math
from collections import defaultdict
from map.hex_tile import HexTile, terrain_colors

class HexGridRenderer(arcade.Window):
    def __init__(self, width=800, height=600, title="Hex Grid Renderer"):
        super().__init__(width, height, title)
        self.tiles = []
        self.tile_info = []
        self.width = width
        self.height = height
        self.center_x = width / 2
        self.center_y = height / 2
        self.base_tile_size = 5  # Size of the hex tile
        self.tile_size = self.base_tile_size
        self.queue = None
        self.selected_tile: Optional[HexTile] = None
        self.buckets = defaultdict(list)  # Buckets for spatial partitioning
        self.bucket_size = self.tile_size * 20  # Adjust size as needed
        self.tile_map = {}
        self.tile_positions = {}
        self.zoom = 1.0
        self.zoom_speed = 0.1

        self.inv_tile_size = 1 / self.tile_size
        self.hex_height = (3 ** 0.5) / 2 * self.tile_size
        self.hex_width = 1.5 * self.tile_size

    def setup(self, tiles, queue):
        self.tiles = tiles
        self.tile_map = {(tile.q, tile.r): tile for tile in tiles}
        self.tile_positions = {(tile.q, tile.r): self.get_tile_position(tile) for tile in tiles}
        self.queue = queue
        self.create_buckets()

    def create_buckets(self):
        """Place each tile into a grid-based bucket."""
        for tile in self.tiles:
            tile_x, tile_y = self.get_tile_position(tile)
            bucket_x = int(tile_x // self.bucket_size)
            bucket_y = int(tile_y // self.bucket_size)
            self.buckets[(bucket_x, bucket_y)].append(tile)

    def on_draw(self):
        arcade.start_render()
        for tile in self.tiles:
            self.draw_tile(tile)
        if self.selected_tile:
            self.draw_tile_info(self.selected_tile)
            self.draw_tile_highlight(self.selected_tile)

    def on_mouse_press(self, x, y, button, modifiers):
        new_selected_tile = self.get_tile_at_position(x, y)
        if new_selected_tile != self.selected_tile:
            self.selected_tile = new_selected_tile
            self.on_draw()
            print(f"Selected tile: {self.selected_tile.q}, {self.selected_tile.r}")

    def get_tile_position(self, tile: HexTile):
        """Calculate the screen position of the hex tile."""
        x = self.center_x + (tile.q * self.tile_size * 1.5)
        y = self.center_y + (tile.r * self.tile_size * (3 ** 0.5) + (tile.q * self.tile_size * (3 ** 0.5) / 2))
        return x, y
    
    def get_tile_at_position(self, x, y) -> Optional[HexTile]:
        # Convert screen coordinates (x, y) to axial hex coordinates (q, r)
        q, r = self.pixel_to_axial(x, y)

        # Round to the nearest hex coordinates
        q, r = self.round_axial(q, r)

        # Check if a tile exists at those coordinates
        return self.tile_map.get((q, r))
    
    def pixel_to_axial(self, x, y):
        """Convert pixel coordinates to axial coordinates."""
        dx = (x - self.center_x) * self.inv_tile_size
        dy = (y - self.center_y) * self.inv_tile_size

        q = (2 / 3) * dx
        r = (-1 / 3) * dx + (dy * (3 ** 0.5) / 3)
        return q, r

    
    def round_axial(self, q, r):
        """Round fractional axial coordinates to the nearest hex."""
        cube_x = q
        cube_z = r
        cube_y = -cube_x - cube_z

        rx = round(cube_x)
        ry = round(cube_y)
        rz = round(cube_z)

        x_diff = abs(rx - cube_x)
        y_diff = abs(ry - cube_y)
        z_diff = abs(rz - cube_z)

        if x_diff > y_diff and x_diff > z_diff:
            rx = -ry - rz
        elif y_diff > z_diff:
            ry = -rx - rz

        return rx, rz

    def draw_tile_highlight(self, tile: HexTile):
        # Calculate the position of the tile
        x, y = self.get_tile_position(tile)
        
        # Draw the hexagon
        arcade.draw_polygon_filled(self.hexagon_points(x, y, self.tile_size), arcade.color.YELLOW)

    def draw_tile_info(self, tile: HexTile):
        # draw text info about the tile bottom right of screen
        tile_info = [f"Tile: {tile.q}, {tile.r}",
                     f"Terrain: {tile.terrain_type}",
                     f"Height: {tile.elevation}",
                     f"Moisture: {tile.moisture}"]
        font_size = 12
        arcade.draw_text("\n".join(tile_info), self.width + 10, self.height - 20,
                         arcade.color.WHITE, font_size=font_size, anchor_x="right", 
                        multiline=True, width=self.width)

    def draw_tile(self, tile: HexTile):
        # Calculate the position of the tile
        x, y = self.tile_positions.get((tile.q, tile.r))
        
        color = terrain_colors.get(tile.terrain_type, arcade.color.WHITE)
        
        # Draw the hexagon
        arcade.draw_polygon_filled(self.hexagon_points(x, y, self.tile_size), color)

    def hexagon_points(self, x, y, size):
        """Generate the points of a hexagon centered at (x, y) with high precision."""
        # Convert size to Decimal for precise calculations
        points = []
        for i in range(6):
            angle_deg = 60 * i
            angle_rad = math.radians(angle_deg)
            points.append((
                x + size * math.cos(angle_rad),
                y + size * math.sin(angle_rad)
            ))
        return points

    def update_tiles(self, tiles):
        self.tiles = tiles
        self.on_draw()

    def run(self):
        arcade.schedule(self.check_queue, 1/60)
        arcade.run()

    def check_queue(self, delta_time):
        if not self.queue.empty():
            tiles = self.queue.get()
            self.update_tiles(tiles)

def start_renderer(queue, tiles):
    renderer = HexGridRenderer()
    renderer.setup(tiles, queue)
    renderer.run()