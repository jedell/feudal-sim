#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <raylib.h>
#include <iostream>
#include <vector>
#include <unordered_map>
#include <cmath>
#include <optional>
#include <string>
#include <map>
#include <limits>
#include <mutex>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

namespace py = pybind11;

std::mutex tile_mutex;

// Hash function for std::pair<int, int>
namespace std {
    template <>
    struct hash<std::pair<int, int>> {
        std::size_t operator()(const std::pair<int, int>& p) const {
            auto hash1 = std::hash<int>{}(p.first);
            auto hash2 = std::hash<int>{}(p.second);
            return hash1 ^ (hash2 << 1);
        }
    };
}

enum class HexTileType {
    GRASSLAND,
    TUNDRA,
    RIVER,
    LAKE,
    OCEAN,
    MOUNTAIN,
    HILL,
    DESERT,
    TEMPERATE_FOREST,
    SWAMP,
    BOREAL_FOREST,
    STEPPE,
    RAINFOREST,
    ICE_CAP
};

#ifdef GOLD
#undef GOLD
#endif

enum class HexResourceType {
    NONE,
    FOOD,
    MATERIAL,
    METAL,
    GOLD
};

// map enum to string
std::map<HexTileType, std::string> hex_tile_type_to_string = {
    {HexTileType::GRASSLAND, "GRASSLAND"},
    {HexTileType::TUNDRA, "TUNDRA"},
    {HexTileType::RIVER, "RIVER"},
    {HexTileType::LAKE, "LAKE"},
    {HexTileType::OCEAN, "OCEAN"},
    {HexTileType::MOUNTAIN, "MOUNTAIN"},
    {HexTileType::HILL, "HILL"},
    {HexTileType::DESERT, "DESERT"},
    {HexTileType::TEMPERATE_FOREST, "TEMPERATE_FOREST"},
    {HexTileType::SWAMP, "SWAMP"},
    {HexTileType::BOREAL_FOREST, "BOREAL_FOREST"},
    {HexTileType::STEPPE, "STEPPE"},
    {HexTileType::RAINFOREST, "RAINFOREST"},
    {HexTileType::ICE_CAP, "ICE_CAP"}
};

std::map<HexResourceType, std::string> hex_resource_type_to_string = {
    {HexResourceType::NONE, "NONE"},
    {HexResourceType::FOOD, "FOOD"},
    {HexResourceType::MATERIAL, "MATERIAL"},
    {HexResourceType::METAL, "METAL"},
    {HexResourceType::GOLD, "GOLD"}
};

std::map<HexTileType, Color> terrain_colors = {
    {HexTileType::GRASSLAND, Color{154, 205, 50, 255}},    // Yellow-green
    {HexTileType::TUNDRA, Color{224, 228, 204, 255}},      // Light grayish-green
    {HexTileType::RIVER, Color{70, 130, 180, 255}},        // Steel blue
    {HexTileType::LAKE, Color{0, 153, 183, 255}},         // Mediterranean Sea blue
    {HexTileType::OCEAN, Color{64, 164, 223, 255}},         // Bright blue
    {HexTileType::MOUNTAIN, Color{139, 137, 137, 255}},    // Dark gray
    {HexTileType::HILL, Color{160, 182, 133, 255}},        // Sage green
    {HexTileType::DESERT, Color{210, 180, 140, 255}},      // Tan
    {HexTileType::TEMPERATE_FOREST, Color{34, 139, 34, 255}},  // Forest green
    {HexTileType::SWAMP, Color{75, 111, 68, 255}},         // Dark moss green
    {HexTileType::BOREAL_FOREST, Color{95, 115, 62, 255}},  // Dark olive green
    {HexTileType::STEPPE, Color{173, 185, 107, 255}},        // Greenish yellow
    {HexTileType::RAINFOREST, Color{0, 128, 0, 255}},        // Dark green
    {HexTileType::ICE_CAP, Color{139, 137, 137, 255}}        // Dark gray
};

// Resource node types (matching Python enum)
enum class ResourceNodeType {
    NONE = 0,
    GOLD_MINE = 1,
    IRON_DEPOSIT = 2,
    STONE_QUARRY = 3,
    RARE_HERBS = 4
};

// Resource node colors
std::map<ResourceNodeType, Color> resource_colors = {
    {ResourceNodeType::GOLD_MINE, Color{255, 215, 0, 200}},      // Gold
    {ResourceNodeType::IRON_DEPOSIT, Color{169, 169, 169, 200}}, // Silver/Gray
    {ResourceNodeType::STONE_QUARRY, Color{105, 105, 105, 200}}, // Dim Gray
    {ResourceNodeType::RARE_HERBS, Color{0, 255, 127, 200}}      // Spring Green
};

// Resource node symbols
std::map<ResourceNodeType, std::string> resource_symbols = {
    {ResourceNodeType::GOLD_MINE, "Au"},
    {ResourceNodeType::IRON_DEPOSIT, "Fe"},
    {ResourceNodeType::STONE_QUARRY, "St"},
    {ResourceNodeType::RARE_HERBS, "Hb"}
};

#pragma pack(push, 1)
struct HexTile {
    int q, r;
    HexTileType terrain_type;
    float elevation;
    float moisture;
    float temperature;
    float food_output;
    float material_output;
    float metal_output;
    int population_capacity;
    std::array<char, 50> owner;
    std::array<unsigned char, 4> owner_color;
    bool operator==(const HexTile& other) const {
        return q == other.q && r == other.r && terrain_type == other.terrain_type &&
               elevation == other.elevation && moisture == other.moisture && temperature == other.temperature;
    }

    bool operator!=(const HexTile& other) const {
        return !(*this == other);
    }

    py::tuple __getstate__() const {
        return py::make_tuple(
            q,
            r,
            terrain_type,
            elevation,
            moisture,
            temperature,
            food_output,
            material_output,
            metal_output,
            population_capacity,
            std::string(owner.data()),
            owner_color
        );
    }

    static HexTile __setstate__(py::tuple t) {
        if (t.size() != 12)
            throw std::runtime_error("Invalid state!");

        HexTile tile;
        tile.q = t[0].cast<int>();
        tile.r = t[1].cast<int>();
        tile.terrain_type = t[2].cast<HexTileType>();
        tile.elevation = t[3].cast<float>();
        tile.moisture = t[4].cast<float>();
        tile.temperature = t[5].cast<float>();
        tile.food_output = t[6].cast<float>();
        tile.material_output = t[7].cast<float>();
        tile.metal_output = t[8].cast<float>();
        tile.population_capacity = t[9].cast<int>();
        strncpy(tile.owner.data(), t[10].cast<std::string>().c_str(), sizeof(tile.owner));
        tile.owner[sizeof(tile.owner) - 1] = '\0'; // Ensure null-termination
        tile.owner_color = t[11].cast<std::array<unsigned char, 4>>();
        return tile;
    }
};
#pragma pack(pop)

#pragma pack(push, 1)
struct House {
    std::array<char, 50> name;
    std::array<unsigned char, 4> color;
    float food;
    float material;
    float metal;
    int population;
    int military_power;
};
#pragma pack(pop)

class HexGridRenderer {
    int width, height;
    float center_x, center_y;
    float base_tile_size, tile_size;
    float zoom, zoom_speed;
    float inv_tile_size, hex_height, hex_width;
    float pan_x, pan_y;
    float min_zoom, max_zoom;
    std::shared_ptr<std::vector<HexTile>> tiles;
    std::unordered_map<std::pair<int, int>, HexTile> tile_map;
    std::unordered_map<std::pair<int, int>, std::pair<float, float>> tile_positions;
    std::optional<HexTile*> selected_tile;
    std::string title;
    Camera2D camera;
    std::shared_ptr<std::vector<House>> houses;

    // flags
    bool show_territory = false;
    bool show_resources = true;
public:
    HexGridRenderer(int width = 800, int height = 600, const std::string& title = "Hex Grid Renderer")
        : width(width), height(height), title(title) {
        center_x = width / 2;
        center_y = height / 2;
        base_tile_size = 30; // Adjusted tile size for better visibility
        tile_size = base_tile_size;
        zoom = 1.0;
        zoom_speed = 0.025; // Adjusted zoom speed for smoother zooming
        inv_tile_size = 1.0 / tile_size;
        hex_height = (std::sqrt(3.0) / 2 ) * tile_size;
        hex_width = 1.5 * tile_size;

        camera.target = { center_x, center_y };
        camera.offset = { center_x, center_y };
        camera.rotation = 0.0f;
        camera.zoom = 1.0f;
        min_zoom = 1.0f;
        max_zoom = 3.0f;
    }

    void setup(const std::vector<HexTile>& new_tiles) {
        this->tiles = std::make_shared<std::vector<HexTile>>(new_tiles);
        for (const auto& tile : *tiles) {
            tile_map[{tile.q, tile.r}] = tile;
            tile_positions[{tile.q, tile.r}] = get_tile_position(tile);
        }
        calculate_initial_zoom_and_pan();
    }

    std::shared_ptr<std::vector<HexTile>> get_tiles() {
        return tiles;
    }

    // func to init shared memory for house data, similar to tile shared memory
    House* init_house_shared_memory(
        const char* shared_memory_name, size_t memory_size, int num_houses
    ) {
        int fd = shm_open(shared_memory_name, O_CREAT | O_RDWR, 0666);
        if (fd == -1) {
            perror("shm_open failed");
            close(fd);
            return nullptr;
        }
        ftruncate(fd, memory_size);
        void* mapped_memory = mmap(nullptr, memory_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (mapped_memory == MAP_FAILED) {
            perror("mmap failed");
            close(fd);
            return nullptr;
        }
        return static_cast<House*>(mapped_memory);
    }

    void run(
        const char* shared_memory_name, size_t memory_size, int num_tiles, 
        const char* house_shared_memory_name, size_t house_memory_size, int num_houses
    ) {
        std::cout << "DEBUG: Tile size: " << sizeof(HexTile) << std::endl;
        std::cout << "DEBUG: House size: " << sizeof(House) << std::endl;
        usleep(500000);
        int fd = shm_open(shared_memory_name, O_RDONLY, 0666);
        if (fd == -1) {
            perror("shm_open failed");
            close(fd);
            return;
        }

        void* mapped_memory = mmap(nullptr, memory_size, PROT_READ, MAP_SHARED, fd, 0);
        if (mapped_memory == MAP_FAILED) {
            perror("mmap failed");
            close(fd);
            return;
        }

        HexTile* tile_data = static_cast<HexTile*>(mapped_memory);
        if (tile_data == MAP_FAILED) {
            perror("mmap failed");
            close(fd);
            return;
        }

        assert(memory_size % sizeof(HexTile) == 0);
        assert(memory_size / sizeof(HexTile) == num_tiles);
        std::unordered_map<std::pair<int, int>, HexTile*> shared_tile_map;
        for (int i = 0; i < memory_size / sizeof(HexTile); ++i) {
            HexTile* tile = &tile_data[i];
            shared_tile_map[{tile->q, tile->r}] = tile;
        }
        assert(shared_tile_map.size() == num_tiles);

        House* house_data = init_house_shared_memory(house_shared_memory_name, house_memory_size, num_houses);
        if (!house_data) {
            std::cerr << "Failed to initialize house shared memory" << std::endl;
            return;
        }

        InitWindow(width, height, title.c_str());
        SetTargetFPS(60);

        while (!WindowShouldClose()) {
            handle_input();
            BeginDrawing();
            ClearBackground(RAYWHITE);

            BeginMode2D(camera);

            for (int i = 0; i < memory_size / sizeof(HexTile); ++i) {
                HexTile* tile = &tile_data[i];
                draw_tile(*tile);
            }

            on_mouse_hover(shared_tile_map);
            if (selected_tile) {
                draw_tile_highlight(*selected_tile);
            }

            EndMode2D();

            if (selected_tile) {
                draw_tile_info(*selected_tile);
            }

            draw_house_info(house_data, num_houses);
            
            // Draw controls/status
            std::string controls = "WASD: Move  Mouse Wheel: Zoom  T: Territory  R: Resources";
            DrawText(controls.c_str(), 20, height - 20, 10, DARKGRAY);
            
            EndDrawing();
        }
        munmap(tile_data, memory_size);
        close(fd);

        CloseWindow();
    }

    py::tuple __getstate__() const {
        // Return a tuple that fully encodes the state of the object
        return py::make_tuple(
            *tiles,
            tile_map,
            tile_positions,
            camera.target.x,
            camera.target.y,
            camera.zoom,
            min_zoom,
            max_zoom
        );
    }

    static HexGridRenderer __setstate__(py::tuple t) {
        if (t.size() != 8)
            throw std::runtime_error("Invalid state!");

        // Create a new C++ instance
        HexGridRenderer r;
        //encode state of object
        r.tiles = std::make_shared<std::vector<HexTile>>(t[0].cast<std::vector<HexTile>>());
        r.tile_map = t[1].cast<std::unordered_map<std::pair<int, int>, HexTile>>();
        r.tile_positions = t[2].cast<std::unordered_map<std::pair<int, int>, std::pair<float, float>>>();
        r.camera.target.x = t[3].cast<float>();
        r.camera.target.y = t[4].cast<float>();
        r.camera.zoom = t[5].cast<float>();
        r.min_zoom = t[6].cast<float>();
        r.max_zoom = t[7].cast<float>();
        return r;
    }

    std::vector<std::pair<int, int>> get_neighbors(int q, int r) {
       return {
           {q + 1, r}, {q - 1, r}, {q, r + 1}, {q, r - 1}, {q + 1, r - 1}, {q - 1, r + 1}
       };
    }

    // function to compare array of chars as strings
    bool compare_owner(const std::array<char, 50>& owner1, const std::array<char, 50>& owner2) {
        return std::string(owner1.data()) == std::string(owner2.data());
    }

    // Resource node helper functions (matching Python logic)
    ResourceNodeType get_resource_node_type(const HexTile& tile) {
        if (tile.metal_output > 100) {
            int resource_code = static_cast<int>(tile.metal_output) - 100;
            if (resource_code >= 1 && resource_code <= 4) {
                return static_cast<ResourceNodeType>(resource_code);
            }
        }
        return ResourceNodeType::NONE;
    }

    float get_base_metal_output(const HexTile& tile) {
        if (tile.metal_output > 100) {
            return fmod(tile.metal_output, 100.0f);
        }
        return tile.metal_output;
    }

    bool has_special_resource(const HexTile& tile) {
        return get_resource_node_type(tile) != ResourceNodeType::NONE;
    }

    void draw_tile(const HexTile& tile) {
        auto [x, y] = get_tile_position(tile);
        Color color = terrain_colors[tile.terrain_type];
        DrawPoly({x, y}, 6, tile_size, 0, color);

        // if tile has owner, draw interior glow on tile in owner color
        if (show_territory) {
            if (!compare_owner(tile.owner, std::array<char, 50>{'N', 'o', 'n', 'e', '\0'})) {
                DrawPoly({x, y}, 6, tile_size, 0, {tile.owner_color[0], tile.owner_color[1], tile.owner_color[2], tile.owner_color[3]});
            }
        }

        // Draw resource nodes if enabled
        if (show_resources && has_special_resource(tile)) {
            draw_resource_node(tile, x, y);
        }
   }

   void draw_resource_node(const HexTile& tile, float x, float y) {
        ResourceNodeType resource_type = get_resource_node_type(tile);
        if (resource_type == ResourceNodeType::NONE) return;

        // Draw resource indicator circle
        Color resource_color = resource_colors[resource_type];
        float resource_radius = tile_size * 0.3f;
        DrawCircle(x, y, resource_radius, resource_color);

        // Draw resource symbol if tile is large enough
        if (tile_size > 20) {
            std::string symbol = resource_symbols[resource_type];
            int font_size = static_cast<int>(tile_size * 0.25f);
            font_size = std::max(8, std::min(font_size, 16)); // Clamp font size
            
            Vector2 text_size = MeasureTextEx(GetFontDefault(), symbol.c_str(), font_size, 1);
            float text_x = x - text_size.x / 2;
            float text_y = y - text_size.y / 2;
            
            DrawText(symbol.c_str(), text_x, text_y, font_size, BLACK);
        }
   }

private:

    std::pair<float, float> get_tile_position(const HexTile& tile) {
        float x = center_x + (tile.q * hex_width);
        float y = center_y + (tile.r * hex_height * 2) + (tile.q * hex_height);
        return {x, y};
    }

    void on_mouse_hover(const std::unordered_map<std::pair<int, int>, HexTile*>& shared_tile_map) {
        Vector2 mouse_pos = GetMousePosition();
        auto new_selected_tile = get_tile_at_position(mouse_pos.x, mouse_pos.y, shared_tile_map);
        
        if (new_selected_tile && (!selected_tile || *new_selected_tile != *selected_tile)) {
            selected_tile = new_selected_tile;
        }
    }


    std::optional<HexTile*> get_tile_at_position(int x, int y, const std::unordered_map<std::pair<int, int>, HexTile*>& shared_tile_map) {
        Vector2 world_pos = GetScreenToWorld2D({(float)x, (float)y}, camera);

        // Convert pixel position to axial hex coordinates
        auto [q, r] = pixel_to_axial(world_pos.x, world_pos.y);
        std::tie(q, r) = round_axial(q, r);

        // Look for the tile in the shared_tile_map using axial coordinates
        auto it = shared_tile_map.find({q, r});
        if (it != shared_tile_map.end()) {
            return it->second;
        }
        return std::nullopt;
    }


    std::pair<float, float> pixel_to_axial(int x, int y) {
        float dx = (x - center_x) * inv_tile_size;
        float dy = (y - center_y) * inv_tile_size;
        float q = (2.0 / 3.0) * dx;
        float r = (-1.0 / 3.0) * dx + (dy * std::sqrt(3.0) / 3.0);
        return {q, r};
    }

    std::pair<int, int> round_axial(float q, float r) {
        float cube_x = q;
        float cube_z = r;
        float cube_y = -cube_x - cube_z;

        int rx = std::round(cube_x);
        int ry = std::round(cube_y);
        int rz = std::round(cube_z);

        float x_diff = std::abs(rx - cube_x);
        float y_diff = std::abs(ry - cube_y);
        float z_diff = std::abs(rz - cube_z);

        if (x_diff > y_diff && x_diff > z_diff) {
            rx = -ry - rz;
        } else if (y_diff > z_diff) {
            ry = -rx - rz;
        }

        return {rx, rz};
    }

    void draw_tile_highlight(HexTile* tile) {
        auto [x, y] = get_tile_position(*tile);
        DrawPolyLines({x, y}, 6, tile_size, 0, WHITE);
    }

    void draw_tile_info(HexTile* tile) {
        std::string info = "Tile: " + std::to_string(tile->q) + ", " + std::to_string(tile->r) +
                           "\nTerrain: " + hex_tile_type_to_string[tile->terrain_type] +
                           "\nHeight: " + std::to_string(tile->elevation) +
                           "\nMoisture: " + std::to_string(tile->moisture) +
                           "\nTemperature: " + std::to_string(tile->temperature) +
                           "\nFood Output: " + std::to_string(tile->food_output) +
                           "\nMaterial Output: " + std::to_string(tile->material_output) +
                           "\nMetal Output: " + std::to_string(get_base_metal_output(*tile)) +
                           "\nPopulation Capacity: " + std::to_string(tile->population_capacity) +
                           "\nOwner: " + std::string(tile->owner.data());
        
        // Add resource node information
        if (has_special_resource(*tile)) {
            ResourceNodeType resource_type = get_resource_node_type(*tile);
            std::string resource_name;
            switch (resource_type) {
                case ResourceNodeType::GOLD_MINE: resource_name = "Gold Mine"; break;
                case ResourceNodeType::IRON_DEPOSIT: resource_name = "Iron Deposit"; break;
                case ResourceNodeType::STONE_QUARRY: resource_name = "Stone Quarry"; break;
                case ResourceNodeType::RARE_HERBS: resource_name = "Rare Herbs"; break;
                default: resource_name = "Unknown Resource"; break;
            }
            info += "\nSpecial Resource: " + resource_name;
        }
        
        DrawText(info.c_str(), 20, height - 180, 9, BLACK);
    }

    void draw_house_info(House* house_data, int num_houses) {
        // Draw a colored box representing the house color
        // Color house_color = {house->color[0], house->color[1], house->color[2], house->color[3]};
        // DrawRectangle(20, height - 100, 10, 10, house_color);
        for (int i = 0; i < num_houses; ++i) {
            House* house = &house_data[i];
            // offset text by 20, 20 + i * 10
            std::string info = "House: " + std::string(house->name.data()) +
                               "\nPopulation: " + std::to_string(house->population) +
                               "\nMilitary Power: " + std::to_string(house->military_power) +
                               "\nResources: " + std::to_string(static_cast<int>(house->food)) + ", " 
                                               + std::to_string(static_cast<int>(house->material)) + ", " 
                                               + std::to_string(static_cast<int>(house->metal));
            DrawText(info.c_str(), 20, 20 + i * 70, 9, BLACK);
        }
    }

    void handle_input() {
        if (IsKeyDown(KEY_A)) camera.target.x -= 10 / camera.zoom;
        if (IsKeyDown(KEY_D)) camera.target.x += 10 / camera.zoom;
        if (IsKeyDown(KEY_S)) camera.target.y += 10 / camera.zoom;
        if (IsKeyDown(KEY_W)) camera.target.y -= 10 / camera.zoom;

        if (IsKeyPressed(KEY_T)) {
            show_territory = !show_territory;
        }

        if (IsKeyPressed(KEY_R)) {
            show_resources = !show_resources;
        }

        float wheel = GetMouseWheelMove();
        if (wheel != 0) {
            Vector2 mouse_pos = GetMousePosition();
            
            Vector2 world_pos_before_zoom = GetScreenToWorld2D(mouse_pos, camera);

            float new_zoom = camera.zoom + wheel * zoom_speed;
            camera.zoom = new_zoom;

            if (camera.zoom < min_zoom) {
                camera.zoom = min_zoom;
            }
            if (camera.zoom > max_zoom) {
                camera.zoom = max_zoom;
            }
            Vector2 world_pos_after_zoom = GetScreenToWorld2D(mouse_pos, camera);

            camera.target.x += world_pos_before_zoom.x - world_pos_after_zoom.x;
            camera.target.y += world_pos_before_zoom.y - world_pos_after_zoom.y;
        }
    }

    void calculate_initial_zoom_and_pan() {
        if (tiles->empty()) return;

        float min_x = std::numeric_limits<float>::max();
        float max_x = std::numeric_limits<float>::min();
        float min_y = std::numeric_limits<float>::max();
        float max_y = std::numeric_limits<float>::min();

        for (const auto& tile : *tiles) {
            auto [x, y] = get_tile_position(tile);
            if (x < min_x) min_x = x;
            if (x > max_x) max_x = x;
            if (y < min_y) min_y = y;
            if (y > max_y) max_y = y;
        }

        float grid_width = max_x - min_x;
        float grid_height = max_y - min_y;

        float zoom_x = width / grid_width;
        float zoom_y = height / grid_height;

        camera.zoom = std::min(zoom_x, zoom_y) * 0.9; // Add some padding

        camera.target.x = (min_x + max_x) / 2;
        camera.target.y = (min_y + max_y) / 2;

        min_zoom = std::min(zoom_x, zoom_y) * 0.9;
        max_zoom = 3.0f;
    }
};

PYBIND11_MODULE(renderer, m) {
    pybind11::class_<HexTile>(m, "HexTile")
        .def(pybind11::init<int, int, HexTileType, float, float, float, float, float, float, int, std::array<char, 50>, std::array<unsigned char, 4>>())
        .def_readwrite("q", &HexTile::q)
        .def_readwrite("r", &HexTile::r)
        .def_readwrite("terrain_type", &HexTile::terrain_type)
        .def_readwrite("elevation", &HexTile::elevation)
        .def_readwrite("moisture", &HexTile::moisture)
        .def_readwrite("temperature", &HexTile::temperature)
        .def_readwrite("food_output", &HexTile::food_output)
        .def_readwrite("material_output", &HexTile::material_output)
        .def_readwrite("metal_output", &HexTile::metal_output)
        .def_readwrite("population_capacity", &HexTile::population_capacity)
        .def_readwrite("owner", &HexTile::owner)
        .def_readwrite("owner_color", &HexTile::owner_color)
        .def(py::pickle(
            [](const HexTile &t) { // __getstate__
                return t.__getstate__();
            },
            [](py::tuple t) { // __setstate__
                return HexTile::__setstate__(t);
            }));

    pybind11::enum_<HexTileType>(m, "HexTileType")
        .value("GRASSLAND", HexTileType::GRASSLAND)
        .value("TUNDRA", HexTileType::TUNDRA)
        .value("RIVER", HexTileType::RIVER)
        .value("LAKE", HexTileType::LAKE)
        .value("OCEAN", HexTileType::OCEAN)
        .value("MOUNTAIN", HexTileType::MOUNTAIN)
        .value("HILL", HexTileType::HILL)
        .value("DESERT", HexTileType::DESERT)
        .value("TEMPERATE_FOREST", HexTileType::TEMPERATE_FOREST)
        .value("SWAMP", HexTileType::SWAMP)
        .value("BOREAL_FOREST", HexTileType::BOREAL_FOREST)
        .value("STEPPE", HexTileType::STEPPE)
        .value("RAINFOREST", HexTileType::RAINFOREST)
        .value("ICE_CAP", HexTileType::ICE_CAP);

    pybind11::enum_<HexResourceType>(m, "HexResourceType")
        .value("NONE", HexResourceType::NONE)
        .value("FOOD", HexResourceType::FOOD)
        .value("MATERIAL", HexResourceType::MATERIAL)
        .value("METAL", HexResourceType::METAL)
        .value("GOLD", HexResourceType::GOLD);

    pybind11::class_<HexGridRenderer>(m, "Renderer")
        .def(pybind11::init<>())
        .def("setup", &HexGridRenderer::setup)
        .def("run", &HexGridRenderer::run, py::call_guard<py::gil_scoped_release>()) 
        .def("render_tile", &HexGridRenderer::draw_tile)
        .def(py::pickle(
            [](const HexGridRenderer &r) { // __getstate__
                return r.__getstate__();
            },
            [](py::tuple t) { // __setstate__
                return HexGridRenderer::__setstate__(t);
            }
        ));
}