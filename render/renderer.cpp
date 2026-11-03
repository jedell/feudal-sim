#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <raylib.h>
#include <iostream>
#include <vector>
#include <unordered_map>
#include <cmath>
#include <cstdlib>
#include <algorithm>
#include <optional>
#include <string>
#include <sstream>
#include <map>
#include <limits>
#include <mutex>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>

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

// Sprite rendering structure for depth sorting
struct SpriteRenderInfo {
    std::string sprite_sheet;
    int sprite_index;
    Vector2 position;
    float scale;
    float depth_y;  // Y position for depth sorting
    Color tint;
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
    float gold;
    int population;
    int population_loyalty;
    int military_power;
    int ravens_in_transit;   // outgoing ravens count
    int at_war;              // number of active wars
};
#pragma pack(pop)

#pragma pack(push, 1)
struct PositionedEntity {
    int q, r;                                    // Position coordinates
    std::array<char, 50> name;                   // Entity name (e.g., "General Snow")
    std::array<char, 50> house_name;             // Parent house name
    std::array<unsigned char, 4> color;          // Display color (from house)
    int entity_type;                             // 0=general, 1=scout, 2=army, 3=merchant, 4=caravan
    int assigned_soldiers;                       // Military strength
    int movement_points;                         // Current movement points
    int max_movement;                            // Maximum movement per turn
    int operational_range;                       // Operational range in tiles
    uint8_t morale;                              // 0-100 group morale
    uint8_t supplies;                            // 0-100 group supplies
    uint8_t equipment_level;                     // 0-100 equipment quality
    std::array<char, 60> orders;                 // Current mission/orders summary
};
#pragma pack(pop)

// City types for tile-based city rendering
enum class CityType {
    NONE = 0,
    CAPITAL = 1,
    TRADE = 2,
    MILITARY = 3,
    AGRICULTURAL = 4,
    OUTPOST = 5
};

// Positioned entity types
enum class EntityType {
    GENERAL = 0,
    SCOUT = 1,
    ARMY = 2,
    MERCHANT = 3,
    CARAVAN = 4
};

struct CityInfo {
    CityType type;
    int development_level;
    int house_id;
};

// Sprite management system
struct SpriteSheet {
    Texture2D texture;
    int sprite_width;
    int sprite_height;
    int cols;
    int rows;
    
    Rectangle get_sprite_rect(int index) const {
        int col = index % cols;
        int row = index / cols;
        return {
            static_cast<float>(col * sprite_width),
            static_cast<float>(row * sprite_height),
            static_cast<float>(sprite_width),
            static_cast<float>(sprite_height)
        };
    }
};

class SpriteManager {
private:
    std::unordered_map<std::string, SpriteSheet> sprite_sheets;
    std::unordered_map<std::string, Texture2D> single_textures;
    
public:
    bool load_sprite_sheet(const std::string& name, const std::string& path, int sprite_width, int sprite_height) {
        // Check if already loaded
        if (sprite_sheets.find(name) != sprite_sheets.end()) {
            std::cout << "Sprite sheet " << name << " already loaded, skipping" << std::endl;
            return true;
        }
        
        if (!std::filesystem::exists(path)) {
            std::cout << "WARNING: Sprite file not found: " << path << std::endl;
            return false;
        }
        
        // Use raylib's texture loading
        Texture2D texture = LoadTexture(path.c_str());
        if (texture.id == 0 || texture.width == 0 || texture.height == 0) {
            std::cout << "ERROR: Failed to load sprite sheet: " << path << std::endl;
            return false;
        }
        
        // Set texture filter to nearest neighbor for pixel-perfect rendering
        SetTextureFilter(texture, TEXTURE_FILTER_POINT);
        
        // Validate sprite dimensions
        if (sprite_width <= 0 || sprite_height <= 0 || 
            sprite_width > texture.width || sprite_height > texture.height) {
            std::cout << "ERROR: Invalid sprite dimensions for " << path 
                     << " (sprite: " << sprite_width << "x" << sprite_height 
                     << ", texture: " << texture.width << "x" << texture.height << ")" << std::endl;
            UnloadTexture(texture);
            return false;
        }
        
        SpriteSheet sheet;
        sheet.texture = texture;
        sheet.sprite_width = sprite_width;
        sheet.sprite_height = sprite_height;
        sheet.cols = texture.width / sprite_width;
        sheet.rows = texture.height / sprite_height;
        
        // Ensure we have at least one sprite
        if (sheet.cols == 0 || sheet.rows == 0) {
            std::cout << "ERROR: No sprites found in " << path << std::endl;
            UnloadTexture(texture);
            return false;
        }
        
        sprite_sheets[name] = sheet;
        std::cout << "Loaded sprite sheet: " << name << " (" << sheet.cols << "x" << sheet.rows << " sprites, " 
                 << texture.width << "x" << texture.height << " texture)" << std::endl;
        return true;
    }
    
    void draw_sprite(const std::string& sheet_name, int sprite_index, Vector2 position, float scale = 1.0f, Color tint = WHITE) {
        auto it = sprite_sheets.find(sheet_name);
        if (it != sprite_sheets.end()) {
            const SpriteSheet& sheet = it->second;
            
            // Bounds check sprite index
            int max_sprites = sheet.cols * sheet.rows;
            if (sprite_index < 0 || sprite_index >= max_sprites) {
                // Use sprite 0 as fallback for invalid indices
                sprite_index = 0;
            }
            
            Rectangle source = sheet.get_sprite_rect(sprite_index);
            Rectangle dest = {
                position.x, position.y,
                sheet.sprite_width * scale,
                sheet.sprite_height * scale
            };
            
            // Use raylib's DrawTexturePro for proper sprite rendering
            DrawTexturePro(sheet.texture, source, dest, {0, 0}, 0.0f, tint);
        }
    }
    
    bool has_sprite_sheet(const std::string& name) const {
        return sprite_sheets.find(name) != sprite_sheets.end();
    }
    
    void draw_animated_sprite(const std::string& sheet_name, Vector2 position, float tile_size, float scale = 1.0f, Color tint = WHITE) {
        auto it = sprite_sheets.find(sheet_name);
        if (it != sprite_sheets.end()) {
            const SpriteSheet& sheet = it->second;
            
            // Animation: cycle through first row (walking down animation)
            // Use raylib's GetTime() for reliable timing
            float current_time = GetTime();
            
            // Animation speed: change frame every 0.4 seconds
            // First row has 4 sprites (columns 0-3 of row 0)
            int frame_count = 4; // Only use first 4 sprites from first row
            int current_frame = (int)(current_time / 0.4f) % frame_count;
            
            Rectangle source = sheet.get_sprite_rect(current_frame);
            
            // Knight sprites are 32x32 pixels - position is already centered by the caller
            Rectangle dest = {
                position.x, position.y,
                sheet.sprite_width * scale,
                sheet.sprite_height * scale
            };
            
            DrawTexturePro(sheet.texture, source, dest, {0, 0}, 0.0f, tint);
        }
    }
    
    ~SpriteManager() {
        for (auto& pair : sprite_sheets) {
            UnloadTexture(pair.second.texture);
        }
        for (auto& pair : single_textures) {
            UnloadTexture(pair.second);
        }
    }
};

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
    
    // Entity data for hover info
    PositionedEntity* current_entity_data;
    int current_num_entities;

    // flags
    bool show_territory = false;
    bool show_resources = true;
    bool show_entity_list = false;        // 'I' key overlay
    bool show_minimap = true;             // 'M' key
    bool show_event_log = false;          // 'L' key
    bool show_turn_stats = true;          // 'Y' key — default on
    bool show_chat = false;               // 'C' key — agent chat inspector
    int chat_agent_index = 0;             // selected agent in chat inspector
    int chat_scroll = 0;                  // scroll offset (wrapped lines)
    int agents_last_seq = -1;             // last seen inspector write_seq
    bool chat_follow = true;              // auto-scroll to newest on update
    int selected_entity_index = -1;       // index into entity_data, -1 = none
    std::vector<bool> house_panels_expanded; // Track which house panels are expanded

    // Minimap cache
    int mm_min_q = 0, mm_max_q = 0, mm_min_r = 0, mm_max_r = 0;
    bool mm_bounds_computed = false;

    // Event log shared memory
    int events_fd = -1;
    void* events_raw = MAP_FAILED;
    static constexpr int EVENTS_MAX = 20;
    static constexpr int EVENT_STR_SIZE = 80;
    static constexpr int EVENTS_TOTAL = 4 + EVENTS_MAX * EVENT_STR_SIZE;

    // Agent inspector shared memory — must match
    // feudal_sim/core/agent_inspector.py byte-for-byte (raw offsets, no padding)
    int agents_fd = -1;
    void* agents_raw = MAP_FAILED;
    static constexpr int AGENTS_MAX = 12;
    static constexpr int AGENTS_HEADER = 28;
    static constexpr int AGENT_SLOT = 29578;
    static constexpr int AGENTS_TOTAL = AGENTS_HEADER + AGENTS_MAX * AGENT_SLOT;
    static constexpr int AO_NAME = 0;
    static constexpr int AO_KIND = 64;
    static constexpr int AO_HOUSE = 80;
    static constexpr int AO_COLOR = 130;
    static constexpr int AO_STATUS = 134;
    static constexpr int AO_OBJECTIVES = 390;
    static constexpr int AO_CHAT_LEN = 902;
    static constexpr int AO_CHAT = 906;
    static constexpr int AGENT_CHAT_MAX = 28672;
    SpriteManager sprite_manager; // Sprite management system
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
        current_entity_data = nullptr;
        current_num_entities = 0;
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
    
private:
    void load_sprites() {
        std::cout << "Loading sprite assets..." << std::endl;
        
        // Load sprites one by one with error checking
        // Start with just Trees.png to test
        if (sprite_manager.load_sprite_sheet("trees", "render/assets/Trees.png", 16, 16)) {
            std::cout << "Successfully loaded trees sprites" << std::endl;
        }
        
        // If trees work, try keeps with a larger sprite size
        if (sprite_manager.load_sprite_sheet("keeps", "render/assets/Keep.png", 32, 32)) {
            std::cout << "Successfully loaded keep sprites" << std::endl;
        }
        
        // Load huts for outposts (assume 16x16 tiles in the sheet)
        if (sprite_manager.load_sprite_sheet("huts", "render/assets/Huts.png", 16, 16)) {
            std::cout << "Successfully loaded huts sprites" << std::endl;
        }
        
        // Try knight sprites
        // RedKnight sprite sheet - try 32x32 pixels per sprite
        if (sprite_manager.load_sprite_sheet("red_knights", "render/assets/Soliders/Mounted/RedKnight.png", 32, 32)) {
            std::cout << "Successfully loaded red knight sprites" << std::endl;
        } else {
            std::cout << "Failed to load red knight sprites" << std::endl;
        }
        if (sprite_manager.load_sprite_sheet("cyan_knights", "render/assets/Soliders/Mounted/CyanKnight.png", 32, 32)) {
            std::cout << "Successfully loaded cyan knight sprites" << std::endl;
        } else {
            std::cout << "Failed to load cyan knight sprites" << std::endl;
        }
        if (sprite_manager.load_sprite_sheet("lime_knights", "render/assets/Soliders/Mounted/LimeKnight.png", 32, 32)) {
            std::cout << "Successfully loaded lime knight sprites" << std::endl;
        } else {
            std::cout << "Failed to load lime knight sprites" << std::endl;
        }
        if (sprite_manager.load_sprite_sheet("purple_knights", "render/assets/Soliders/Mounted/PurpleKnight.png", 32, 32)) {
            std::cout << "Successfully loaded purple knight sprites" << std::endl;
        } else {
            std::cout << "Failed to load purple knight sprites" << std::endl;
        }

        // Load farmer sprites for caravans
        if (sprite_manager.load_sprite_sheet("farmers", "render/assets/FarmerTemplate.png", 16, 32)) {
            std::cout << "Successfully loaded farmer sprites" << std::endl;
        } else {
            std::cout << "Failed to load farmer sprites" << std::endl;
        }
        
        std::cout << "Sprite loading completed." << std::endl;
    }
    
public:

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

    // func to init shared memory for positioned entity data
    PositionedEntity* init_positioned_entities_shared_memory(
        const char* shared_memory_name, size_t memory_size, int num_entities
    ) {
        int fd = shm_open(shared_memory_name, O_CREAT | O_RDWR, 0666);
        if (fd == -1) {
            perror("shm_open positioned entities failed");
            close(fd);
            return nullptr;
        }
        ftruncate(fd, memory_size);
        void* mapped_memory = mmap(nullptr, memory_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (mapped_memory == MAP_FAILED) {
            perror("mmap positioned entities failed");
            close(fd);
            return nullptr;
        }
        return static_cast<PositionedEntity*>(mapped_memory);
    }


    void run(
        const char* shared_memory_name, size_t memory_size, int num_tiles, 
        const char* house_shared_memory_name, size_t house_memory_size, int num_houses,
        const char* entities_shared_memory_name = nullptr, size_t entities_memory_size = 0, int num_entities = 0
    ) {
        std::cout << "DEBUG: Tile size: " << sizeof(HexTile) << std::endl;
        std::cout << "DEBUG: House size: " << sizeof(House) << std::endl;
        std::cout << "DEBUG: PositionedEntity size: " << sizeof(PositionedEntity) << std::endl;
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

        if (memory_size % sizeof(HexTile) != 0) {
            std::cerr << "ERROR: memory_size (" << memory_size << ") is not a multiple of sizeof(HexTile) (" << sizeof(HexTile) << ")" << std::endl;
            munmap(mapped_memory, memory_size);
            close(fd);
            return;
        }
        if (memory_size / sizeof(HexTile) != (size_t)num_tiles) {
            std::cerr << "ERROR: tile count mismatch: memory has " << memory_size / sizeof(HexTile) << " tiles but expected " << num_tiles << std::endl;
            munmap(mapped_memory, memory_size);
            close(fd);
            return;
        }
        std::unordered_map<std::pair<int, int>, HexTile*> shared_tile_map;
        for (int i = 0; i < memory_size / sizeof(HexTile); ++i) {
            HexTile* tile = &tile_data[i];
            shared_tile_map[{tile->q, tile->r}] = tile;
        }
        if (shared_tile_map.size() != (size_t)num_tiles) {
            std::cerr << "WARNING: " << (num_tiles - shared_tile_map.size()) << " duplicate tile coordinates detected (sizeof(HexTile)=" << sizeof(HexTile) << "). Continuing with " << shared_tile_map.size() << " unique tiles." << std::endl;
        }

        House* house_data = init_house_shared_memory(house_shared_memory_name, house_memory_size, num_houses);
        if (!house_data) {
            std::cerr << "Failed to initialize house shared memory" << std::endl;
            return;
        }

        // Initialize positioned entities shared memory (optional)
        PositionedEntity* entity_data = nullptr;
        if (entities_shared_memory_name && num_entities > 0) {
            entity_data = init_positioned_entities_shared_memory(entities_shared_memory_name, entities_memory_size, num_entities);
            if (!entity_data) {
                std::cerr << "Warning: Failed to initialize positioned entities shared memory" << std::endl;
                // Continue without entities - not fatal
            } else {
                std::cout << "DEBUG: Initialized positioned entities shared memory for " << num_entities << " entities" << std::endl;
            }
        }

        // Open event log shared memory (optional — fails silently if Python side not ready)
        events_fd = shm_open("/psm_events", O_RDONLY, 0666);
        if (events_fd != -1) {
            events_raw = mmap(nullptr, EVENTS_TOTAL, PROT_READ, MAP_SHARED, events_fd, 0);
            if (events_raw == MAP_FAILED) {
                close(events_fd);
                events_fd = -1;
            }
        }

        // Open agent inspector shared memory (optional — same pattern)
        agents_fd = shm_open("/psm_agents", O_RDONLY, 0666);
        if (agents_fd != -1) {
            agents_raw = mmap(nullptr, AGENTS_TOTAL, PROT_READ, MAP_SHARED, agents_fd, 0);
            if (agents_raw == MAP_FAILED) {
                close(agents_fd);
                agents_fd = -1;
            }
        }

        // Initialize house panel expansion state
        house_panels_expanded.resize(num_houses, false);
        
        // Store entity data for hover info
        current_entity_data = entity_data;
        current_num_entities = num_entities;

        SetConfigFlags(FLAG_WINDOW_RESIZABLE);
        InitWindow(width, height, title.c_str());
        MaximizeWindow();
        SetTargetFPS(60);
        // ESC is bound to deselect (see handle_input); without this raylib
        // treats ESC as the window-exit key and quits the whole app.
        SetExitKey(KEY_NULL);
        
        // Load sprites after raylib is fully initialized
        load_sprites();

        while (!WindowShouldClose()) {
            // Track window size live so panels layout correctly after
            // resize / maximize / fullscreen transitions
            if (IsWindowResized()) {
                width = GetScreenWidth();
                height = GetScreenHeight();
            }
            handle_input(shared_tile_map);
            BeginDrawing();
            ClearBackground(RAYWHITE);

            BeginMode2D(camera);

            for (int i = 0; i < memory_size / sizeof(HexTile); ++i) {
                HexTile* tile = &tile_data[i];
                draw_tile(*tile);
            }

            // Collect all sprites with depth information and draw in Y-sorted order
            draw_sprites_depth_sorted(tile_data, memory_size / sizeof(HexTile));

            // Draw positioned entities (generals, scouts, etc.)
            if (entity_data && num_entities > 0) {
                for (int i = 0; i < num_entities; ++i) {
                    PositionedEntity* entity = &entity_data[i];
                    // Check for valid position and non-empty name to avoid rendering zeroed-out entities
                    if (entity->q != -1 && entity->r != -1 &&
                        strlen(entity->name.data()) > 0 &&
                        std::string(entity->name.data()).find("__") != 0) { // skip sentinels
                        draw_positioned_entity(*entity);
                    }
                }
            }

            // Contact highlight — pulsing red line between adjacent opposing generals
            if (entity_data && num_entities > 0) {
                float pulse = 0.5f + 0.5f * std::sin(GetTime() * 4.0f);
                for (int ai = 0; ai < num_entities; ++ai) {
                    PositionedEntity* a = &entity_data[ai];
                    if (a->entity_type != 0 || strlen(a->name.data()) == 0) continue;
                    if (std::string(a->name.data()) == "__meta__") continue;
                    for (int bi = ai + 1; bi < num_entities; ++bi) {
                        PositionedEntity* b = &entity_data[bi];
                        if (b->entity_type != 0 || strlen(b->name.data()) == 0) continue;
                        if (std::string(b->name.data()) == "__meta__") continue;
                        // Different house, adjacent tiles (hex distance 1)
                        std::string ha(a->house_name.data()), hb(b->house_name.data());
                        if (ha == hb) continue;
                        int dq = a->q - b->q, dr = a->r - b->r;
                        int dist = (std::abs(dq) + std::abs(dr) + std::abs(-dq-dr)) / 2;
                        if (dist > 1) continue;
                        auto [ax, ay] = get_tile_position_from_coords(a->q, a->r);
                        auto [bx, by] = get_tile_position_from_coords(b->q, b->r);
                        unsigned char alpha = (unsigned char)(180 * pulse + 75);
                        DrawLineEx({ax, ay}, {bx, by}, 3.0f, {220, 30, 30, alpha});
                        // Small sword icon at midpoint
                        float mx = (ax + bx) / 2, my = (ay + by) / 2;
                        DrawCircle((int)mx, (int)my, 5, {220, 30, 30, alpha});
                    }
                }
            }

            on_mouse_hover(shared_tile_map, entity_data, num_entities);
            if (selected_tile) {
                draw_tile_highlight(*selected_tile);
            }

            // Highlight tile of selected entity with a pulsing gold outline
            if (selected_entity_index >= 0 && current_entity_data &&
                selected_entity_index < current_num_entities) {
                PositionedEntity* se = &current_entity_data[selected_entity_index];
                if (strlen(se->name.data()) > 0) {
                    float pulse = 0.5f + 0.5f * std::sin(GetTime() * 3.0f);
                    unsigned char alpha = (unsigned char)(180 + 75 * pulse);
                    auto [sx, sy] = get_tile_position_from_coords(se->q, se->r);
                    DrawPolyLines({sx, sy}, 6, tile_size * 1.05f, 0,
                                  {255, 215, 0, alpha});
                }
            }

            EndMode2D();

            if (selected_tile) {
                draw_tile_info(*selected_tile, entity_data, num_entities);
            }

            draw_house_info(house_data, num_houses);
            draw_entity_inspector();
            draw_entity_list_overlay();
            draw_minimap(tile_data, memory_size / sizeof(HexTile));
            draw_event_log_panel();
            draw_turn_stats_panel(house_data, num_houses, entity_data, num_entities);
            draw_chat_inspector();  // topmost overlay when open
            
            // Draw status indicators (top right); shift left of the entity
            // inspector panel (240px wide at the right edge) when it is open
            bool inspector_open = (selected_entity_index >= 0 && current_entity_data &&
                                   selected_entity_index < current_num_entities);
            int status_x = inspector_open ? width - 410 : width - 150;
            int status_y = 15;
            
            std::string territory_status = show_territory ? "Territory: ON" : "Territory: OFF";
            Color territory_color = show_territory ? GREEN : RED;
            DrawTextEx(GetFontDefault(), territory_status.c_str(), {(float)status_x, (float)status_y}, 10, 1, territory_color);
            
            std::string resources_status = show_resources ? "Resources: ON" : "Resources: OFF";
            Color resources_color = show_resources ? GREEN : RED;
            DrawTextEx(GetFontDefault(), resources_status.c_str(), {(float)status_x, (float)(status_y + 15)}, 10, 1, resources_color);

            // Turn / season from meta entity (name == "__meta__", q=turn, r=season, mp=year)
            if (entity_data && num_entities > 0) {
                const char* season_names[4] = {"Spring", "Summer", "Autumn", "Winter"};
                const Color season_colors[4] = {{100,200,100,255},{255,200,50,255},{210,120,30,255},{180,220,255,255}};
                for (int mi = 0; mi < num_entities; ++mi) {
                    PositionedEntity* me = &entity_data[mi];
                    if (std::string(me->name.data()) == "__meta__" && me->q > 0) {
                        int turn = me->q;
                        int season_idx = std::max(0, std::min(3, me->r));
                        int year = me->movement_points;
                        std::string hud = std::string(season_names[season_idx]) +
                                          " Y" + std::to_string(year) + " T" + std::to_string(turn);
                        DrawTextEx(GetFontDefault(), hud.c_str(),
                                   {(float)status_x, (float)(status_y + 30)}, 10, 1, season_colors[season_idx]);
                        break;
                    }
                }
            }

            // House legend (bottom-left)
            if (house_data && num_houses > 0) {
                int leg_x = 10, leg_y = height - 18 * num_houses - 8;
                for (int hi = 0; hi < num_houses; ++hi) {
                    House* h = &house_data[hi];
                    std::string hname(h->name.data());
                    if (hname.empty() || hname == "None") continue;
                    Color hcol = {h->color[0], h->color[1], h->color[2], 220};
                    int row_y = leg_y + hi * 18;
                    DrawRectangle(leg_x, row_y + 2, 12, 12, hcol);
                    DrawRectangleLines(leg_x, row_y + 2, 12, 12, {0,0,0,180});
                    DrawTextEx(GetFontDefault(), hname.c_str(),
                               {(float)(leg_x + 16), (float)row_y}, 10, 1, WHITE);
                }
            }
            
            // Draw controls panel
            std::string controls = "WASD: Move | Wheel: Zoom | T: Territory | R: Resources | I: Entities | M: Map | L: Events | Y: Stats | C: Agent Chat | F11: Fullscreen";
            Vector2 text_size = MeasureTextEx(GetFontDefault(), controls.c_str(), 10, 1);
            int controls_panel_width = (int)text_size.x + 20;
            int controls_panel_height = 25;
            int controls_x = (width - controls_panel_width) / 2; // Center horizontally
            int controls_y = height - controls_panel_height - 10;
            
            // Controls background
            Color controls_bg = {30, 30, 30, 180};
            Color controls_border = {80, 80, 80, 255};
            DrawRectangle(controls_x, controls_y, controls_panel_width, controls_panel_height, controls_bg);
            DrawRectangleLines(controls_x, controls_y, controls_panel_width, controls_panel_height, controls_border);
            
            float text_x = controls_x + 10;
            DrawTextEx(GetFontDefault(), controls.c_str(), {text_x, (float)(controls_y + 6)}, 10, 1, WHITE);
            
            EndDrawing();
        }
        munmap(tile_data, memory_size);
        close(fd);

        if (events_raw != MAP_FAILED) munmap(events_raw, EVENTS_TOTAL);
        if (events_fd != -1) close(events_fd);
        if (agents_raw != MAP_FAILED) munmap(agents_raw, AGENTS_TOTAL);
        if (agents_fd != -1) close(agents_fd);

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

        // Territory border outline — thin line around owned tiles
        if (show_territory) {
            std::string owner_str(tile.owner.data());
            bool has_owner = !owner_str.empty() && owner_str != "None" &&
                             owner_str.find("PENDING:") != 0;
            if (has_owner) {
                Color border_color = {(unsigned char)(tile.owner_color[0] * 0.6f),
                                      (unsigned char)(tile.owner_color[1] * 0.6f),
                                      (unsigned char)(tile.owner_color[2] * 0.6f), 200};
                DrawPolyLines({x, y}, 6, tile_size - 0.5f, 0, border_color);
            }
        }

        // Draw resource nodes if enabled
        if (show_resources && has_special_resource(tile)) {
            draw_resource_node(tile, x, y);
        }

        // Draw pending outpost construction indicator
        {
            std::string owner_str(tile.owner.data());
            if (owner_str.find("PENDING:") == 0) {
                // Construction indicator — top-right corner of tile, away from the general sprite
                float pulse = 0.6f + 0.4f * std::sin(GetTime() * 3.0f);
                float corner_x = x + tile_size * 0.45f;
                float corner_y = y - tile_size * 0.55f;
                float dot_r = tile_size * 0.12f * pulse;
                Color dot_color = {255, 220, 0, (unsigned char)(220 * pulse)};
                DrawCircle((int)corner_x, (int)corner_y, dot_r + 1, {100, 80, 0, 160});
                DrawCircle((int)corner_x, (int)corner_y, dot_r, dot_color);
            }
        }

        // Trees will be drawn in a separate pass after all tiles

        // City sprites are collected and drawn in a separate depth-sorted pass
    }

   void draw_terrain_sprites(const HexTile& tile) {
        // Draw tree sprites on forest tiles
        if (tile.terrain_type == HexTileType::TEMPERATE_FOREST ||
            tile.terrain_type == HexTileType::BOREAL_FOREST ||
            tile.terrain_type == HexTileType::RAINFOREST) {
            
            if (sprite_manager.has_sprite_sheet("trees")) {
                auto [x, y] = get_tile_position(tile);
                
                // Use different tree sprites based on forest type
                int tree_sprite_index = 1; // Skip the stump (index 0)
                
                if (tile.terrain_type == HexTileType::TEMPERATE_FOREST) {
                    tree_sprite_index = 1; // Green tree
                } else if (tile.terrain_type == HexTileType::BOREAL_FOREST) {
                    tree_sprite_index = 2; // Pine-like tree
                } else if (tile.terrain_type == HexTileType::RAINFOREST) {
                    tree_sprite_index = 3; // Dense canopy tree
                }
                
                // Tree layout constants
                const float TREE_SCALE_RATIO = 40.0f;           // Tile size to tree size ratio
                const int TREE_SPRITE_SIZE = 16;                // Tree sprite dimensions (pixels)
                const float CORNER_TREE_DISTANCE = 0.4f;        // Distance from center to corner trees
                const float EDGE_TREE_DISTANCE = 0.50f;         // Distance from center to edge trees
                const int TREES_PER_TILE = 7;                   // Number of trees per forest tile
                
                // Calculate tree sprite scale and centering
                float sprite_scale = tile_size / TREE_SCALE_RATIO;
                float half_sprite_size = (TREE_SPRITE_SIZE * sprite_scale) / 2.0f;
                
                // Uniform grid pattern positions (centered sprites)
                Vector2 tree_positions[] = {
                    {x - tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y - tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Top left
                    {x + tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y - tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Top right
                    {x - tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y + tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Bottom left  
                    {x + tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y + tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Bottom right
                    {x - half_sprite_size, y - half_sprite_size},                                                                         // Center
                    {x - half_sprite_size, y - tile_size * EDGE_TREE_DISTANCE - half_sprite_size},                                       // Top center
                    {x - half_sprite_size, y + tile_size * EDGE_TREE_DISTANCE - half_sprite_size}                                        // Bottom center
                };
                
                // Draw trees in uniform pattern
                int num_trees = TREES_PER_TILE;
                for (int i = 0; i < num_trees; i++) {
                    // Alternate tree types for variety
                    int varied_tree_index = tree_sprite_index;
                    if (i % 2 == 1 && tree_sprite_index < 3) {
                        varied_tree_index = tree_sprite_index + (i % 2); // Systematic variation
                    }
                    
                    sprite_manager.draw_sprite("trees", varied_tree_index, tree_positions[i], sprite_scale);
                }
            }
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
            
            DrawTextEx(GetFontDefault(), symbol.c_str(), {text_x, text_y}, font_size, 1, BLACK);
        }
   }

   // City detection and rendering functions
   CityInfo get_city_info(const HexTile& tile) {
        if (tile.population_capacity < 1000) {
            return {CityType::NONE, 0, 0};
        }
        
        // Decode city information from population_capacity field
        int encoded = static_cast<int>(tile.population_capacity) - 1000;
        
        int city_type_value = (encoded / 100) % 10;
        int development_level = (encoded / 10) % 10;
        int house_id = encoded % 10;
        
        CityType city_type = CityType::NONE;
        if (city_type_value >= 1 && city_type_value <= 5) {
            city_type = static_cast<CityType>(city_type_value);
        }
        
        // Debug output (uncomment to debug city type issues)
        // std::cout << "City decode: pop_cap=" << tile.population_capacity 
        //           << " encoded=" << encoded << " type_val=" << city_type_value 
        //           << " dev_level=" << development_level << " house_id=" << house_id << std::endl;
        
        return {city_type, development_level, house_id};
   }

   void draw_city_on_tile(const HexTile& tile, const CityInfo& city, float x, float y) {
        // Get city color from tile owner color
        Color city_color = {tile.owner_color[0], tile.owner_color[1], 
                           tile.owner_color[2], tile.owner_color[3]};
        
        // Use keep sprite if available, otherwise fall back to circles
        if (sprite_manager.has_sprite_sheet("keeps")) {
            // Choose keep sprite based on development level (0-5 for 6 keep variants in 3x2 grid)
            int keep_sprite_index = std::min(city.development_level - 1, 5);
            keep_sprite_index = std::max(keep_sprite_index, 0); // Ensure >= 0
            
            // Keep sprites are 32x32 pixels - scale them to fit hex tiles properly
            // For hex tiles, we want the sprite to be about 70% of the tile size to look good
            float sprite_scale = (tile_size * 0.7f) / 32.0f; // 32px sprite scaled to 70% of tile
            
            // Center the sprite on the hex tile
            Vector2 sprite_pos = {
                x - (32 * sprite_scale / 2),  // 32px is the actual sprite width
                y - (32 * sprite_scale / 2)   // 32px is the actual sprite height
            };
            
            // Draw a subtle glow behind the city that scales with the sprite
            float glow_radius = (32 * sprite_scale) * 0.6f;
            Color glow_color = {city_color.r, city_color.g, city_color.b, 60};
            DrawCircle(x, y, glow_radius, glow_color);
            
            // Draw keep sprite without any tinting
            sprite_manager.draw_sprite("keeps", keep_sprite_index, sprite_pos, sprite_scale);
        } else {
            // Fallback to original circle rendering
            float base_radius = tile_size * 0.25f;
            float city_radius = base_radius + (city.development_level * 3);
            
            // Draw glow effect behind city
            float glow_radius = city_radius + 4;
            Color glow_color = {city_color.r, city_color.g, city_color.b, 60};
            DrawCircle(x, y, glow_radius, glow_color);
            
            // Draw multiple rings for higher development levels
            for (int i = 1; i <= city.development_level; i++) {
                float ring_radius = base_radius + (i * 2);
                int alpha = 255 - (i * 30); // Fade outer rings
                Color ring_color = {city_color.r, city_color.g, city_color.b, (unsigned char)std::max(80, alpha)};
                DrawCircle(x, y, ring_radius, ring_color);
                DrawCircleLines(x, y, ring_radius, BLACK);
            }
            
            // Draw white background circle for symbol visibility  
            float symbol_bg_radius = base_radius * 0.7f;
            DrawCircle(x, y, symbol_bg_radius, {255, 255, 255, 200});
            DrawCircleLines(x, y, symbol_bg_radius, BLACK);
            
            // Draw city symbol based on type
            int codepoint = get_city_codepoint(city.type);
            if (tile_size > 10) {
                // Scale font size with development level
                int base_font_size = static_cast<int>(tile_size * 0.25f);
                int font_size = base_font_size + (city.development_level * 1);
                font_size = std::max(8, std::min(font_size, 16));
                
                // Get glyph info for positioning
                int utf8Size;
                const char* utf8_text = CodepointToUTF8(codepoint, &utf8Size);
                Vector2 glyph_size = MeasureTextEx(GetFontDefault(), utf8_text, font_size, 1);
                float text_x = x - glyph_size.x / 2;
                float text_y = y - glyph_size.y / 2;
                
                // Use dark text on white background for better visibility
                DrawTextCodepoint(GetFontDefault(), codepoint, {text_x + 1, text_y + 1}, font_size, DARKGRAY); // Slight shadow
                DrawTextCodepoint(GetFontDefault(), codepoint, {text_x, text_y}, font_size, BLACK);
            }
        }
   }

   int get_city_codepoint(CityType city_type) {
        switch (city_type) {
            case CityType::CAPITAL: return 0x265A;      // ♚ Black King (Capital)
            case CityType::TRADE: return 0x2666;        // ♦ Black Diamond (Trade)
            case CityType::MILITARY: return 0x2694;     // ⚔ Crossed Swords (Military)
            case CityType::AGRICULTURAL: return 0x2660; // ♠ Black Spade (Agricultural)
            case CityType::OUTPOST: return 0x2691;      // ⚑ White Flag (Outpost)
            default: return 0x25CF;                     // ● Black Circle
        }
   }

   std::string get_city_type_name(CityType city_type) {
        switch (city_type) {
            case CityType::CAPITAL: return "Capital";
            case CityType::TRADE: return "Trade City";
            case CityType::MILITARY: return "Military Fortress";
            case CityType::AGRICULTURAL: return "Agricultural Center";
            case CityType::OUTPOST: return "Outpost";
            default: return "Unknown";
        }
   }

   std::string get_city_development_name(int level) {
        switch (level) {
            case 1: return "Outpost";
            case 2: return "Village";
            case 3: return "Walled Town";
            case 4: return "Castle";
            case 5: return "City";
            default: return "Unknown";
        }
   }

    void collect_tree_sprites(const HexTile& tile, std::vector<SpriteRenderInfo>& sprites) {
        // Only collect from forest tiles
        if (!(tile.terrain_type == HexTileType::TEMPERATE_FOREST ||
              tile.terrain_type == HexTileType::BOREAL_FOREST ||
              tile.terrain_type == HexTileType::RAINFOREST)) {
            return;
        }
        
        if (!sprite_manager.has_sprite_sheet("trees")) return;
        
        auto [x, y] = get_tile_position(tile);
        
        // Use same tree selection logic as before
        int tree_sprite_index = 1; // Skip the stump (index 0)
        if (tile.terrain_type == HexTileType::TEMPERATE_FOREST) {
            tree_sprite_index = 1; // Green tree
        } else if (tile.terrain_type == HexTileType::BOREAL_FOREST) {
            tree_sprite_index = 2; // Pine-like tree
        } else if (tile.terrain_type == HexTileType::RAINFOREST) {
            tree_sprite_index = 3; // Dense canopy tree
        }
        
        // Same constants as before
        const float TREE_SCALE_RATIO = 40.0f;
        const int TREE_SPRITE_SIZE = 16;
        const float CORNER_TREE_DISTANCE = 0.4f;
        const float EDGE_TREE_DISTANCE = 0.50f;
        const int TREES_PER_TILE = 7;
        
        float sprite_scale = tile_size / TREE_SCALE_RATIO;
        float half_sprite_size = (TREE_SPRITE_SIZE * sprite_scale) / 2.0f;
        
        // Same tree positions as before
        Vector2 tree_positions[] = {
            {x - tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y - tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Top left
            {x + tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y - tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Top right
            {x - tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y + tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Bottom left  
            {x + tile_size * CORNER_TREE_DISTANCE - half_sprite_size, y + tile_size * CORNER_TREE_DISTANCE - half_sprite_size},  // Bottom right
            {x - half_sprite_size, y - half_sprite_size},                                                                         // Center
            {x - half_sprite_size, y - tile_size * EDGE_TREE_DISTANCE - half_sprite_size},                                       // Top center
            {x - half_sprite_size, y + tile_size * EDGE_TREE_DISTANCE - half_sprite_size}                                        // Bottom center
        };
        
        // Add all trees to sprite collection
        for (int i = 0; i < TREES_PER_TILE; i++) {
            int varied_tree_index = tree_sprite_index;
            if (i % 2 == 1 && tree_sprite_index < 3) {
                varied_tree_index = tree_sprite_index + (i % 2);
            }
            
            sprites.push_back({
                "trees",
                varied_tree_index,
                tree_positions[i],
                sprite_scale,
                tree_positions[i].y,  // Use Y position for depth
                WHITE
            });
        }
    }

    void collect_city_sprites(const HexTile& tile, std::vector<SpriteRenderInfo>& sprites) {
        CityInfo city = get_city_info(tile);
        if (city.type == CityType::NONE) return;
        
        auto [x, y] = get_tile_position(tile);
        
        if (city.type == CityType::OUTPOST && sprite_manager.has_sprite_sheet("huts")) {
            // Use the second hut sprite (index 1) for outposts
            int hut_index = 1;
            float sprite_scale = (tile_size * 0.5f) / 16.0f; // huts are 16px; slightly smaller than keeps
            Vector2 sprite_pos = { x - (16 * sprite_scale / 2), y - (16 * sprite_scale / 2) };
            sprites.push_back({
                "huts",
                hut_index,
                sprite_pos,
                sprite_scale,
                y,
                WHITE
            });
        } else if (sprite_manager.has_sprite_sheet("keeps")) {
            // Same keep sprite logic as before for cities
            int keep_sprite_index = std::min(city.development_level - 1, 5);
            keep_sprite_index = std::max(keep_sprite_index, 0);
            float sprite_scale = (tile_size * 0.7f) / 32.0f;
            Vector2 sprite_pos = { x - (32 * sprite_scale / 2), y - (32 * sprite_scale / 2) };
            sprites.push_back({
                "keeps",
                keep_sprite_index,
                sprite_pos,
                sprite_scale,
                y,
                WHITE
            });
        }
    }

    void draw_sprites_depth_sorted(HexTile* tiles, int num_tiles) {
        std::vector<SpriteRenderInfo> sprites_to_draw;
        
        // Collect all sprites from trees and cities
        for (int i = 0; i < num_tiles; ++i) {
            HexTile* tile = &tiles[i];
            collect_tree_sprites(*tile, sprites_to_draw);
            collect_city_sprites(*tile, sprites_to_draw);
        }
        
        // Sort sprites by Y position (higher Y = drawn later = appears in front)
        std::sort(sprites_to_draw.begin(), sprites_to_draw.end(), 
                  [](const SpriteRenderInfo& a, const SpriteRenderInfo& b) {
                      return a.depth_y < b.depth_y;
                  });
        
        // Draw all sprites in depth order
        for (const auto& sprite : sprites_to_draw) {
            sprite_manager.draw_sprite(sprite.sprite_sheet, sprite.sprite_index, 
                                     sprite.position, sprite.scale, sprite.tint);
        }
    }

   void draw_positioned_entity(const PositionedEntity& entity) {
        auto [x, y] = get_tile_position_from_coords(entity.q, entity.r);
        
        // Get entity color
        Color entity_color = {entity.color[0], entity.color[1], entity.color[2], entity.color[3]};
        
        // Define entity radius for use in troop text positioning
        float entity_radius = tile_size * 0.4f;
        
        // Try to use knight sprites for generals
        std::string knight_sprite_sheet = "red_knights"; // Default
        
        // Choose knight sprite color based on entity color (simple color matching)
        if (entity_color.r > 200 && entity_color.g < 100 && entity_color.b < 100) {
            knight_sprite_sheet = "red_knights";
        } else if (entity_color.g > 200 && entity_color.r < 100 && entity_color.b < 100) {
            knight_sprite_sheet = "lime_knights";
        } else if (entity_color.b > 200 && entity_color.r < 100 && entity_color.g < 100) {
            knight_sprite_sheet = "cyan_knights";
        } else if (entity_color.r > 150 && entity_color.b > 150 && entity_color.g < 100) {
            knight_sprite_sheet = "purple_knights";
        }
        
        // Handle caravan rendering with farmer sprites (convoy effect)
        // Fall back to farmer sheet or red_knights if farmers not loaded
        std::string caravan_sheet = sprite_manager.has_sprite_sheet("farmers") ? "farmers" : "red_knights";
        if (entity.entity_type == 4 && sprite_manager.has_sprite_sheet(caravan_sheet)) { // CARAVAN
            // Use farmer sprites in a convoy formation
            // FarmerTemplate.png: 16x24 pixel sprites, first row has walking animation
            float sprite_scale = tile_size / 50.0f; // Smaller than other units to fit multiple
            
            // Convoy formation: 3 farmers in a line to represent caravan
            const int CARAVAN_SIZE = 3;
            float convoy_spacing = tile_size * 0.3f; // Space between convoy members
            
            // Calculate starting position to center the convoy
            float start_x = x - (convoy_spacing * (CARAVAN_SIZE - 1)) / 2;
            
            for (int i = 0; i < CARAVAN_SIZE; i++) {
                // Position each farmer sprite in convoy formation
                Vector2 farmer_pos = {
                    start_x + (i * convoy_spacing) - (16 * sprite_scale / 2), // Center 16px sprite
                    y - (32 * sprite_scale / 2) // Center 32px sprite vertically
                };
                
                // Use different walking animation frames for variety
                // First row of FarmerTemplate.png has walking down animation (frames 0-4)
                int frame_offset = i % 5; // Cycle through frames 0-4
                float animation_time = GetTime() + (i * 0.2f); // Stagger animations
                int current_frame = (int)(animation_time / 0.4f) % 5; // 5 frames in first row
                int sprite_index = (current_frame + frame_offset) % 5; // First row only
                
                // Draw farmer sprite with entity color tint for house identification
                Color farmer_tint = {entity_color.r, entity_color.g, entity_color.b, 200};
                sprite_manager.draw_sprite(caravan_sheet, sprite_index, farmer_pos, sprite_scale, farmer_tint);
            }
        }
        // Use knight sprite for generals — fall back to red_knights with color tint if variant not loaded
        else if (entity.entity_type == 0 && sprite_manager.has_sprite_sheet("red_knights")) { // GENERAL
            // Use the specific colored sheet if loaded, otherwise use red_knights tinted with entity color
            bool has_variant = sprite_manager.has_sprite_sheet(knight_sprite_sheet);
            std::string draw_sheet = has_variant ? knight_sprite_sheet : "red_knights";

            float sprite_scale = tile_size / 40.0f;
            Vector2 sprite_pos = {
                x - (32 * sprite_scale / 2),
                y - (32 * sprite_scale / 2)
            };

            sprite_manager.draw_animated_sprite(draw_sheet, sprite_pos, tile_size, sprite_scale);
        } else {
            // Fallback to original circle rendering
            
            // Draw glow effect behind entity
            float glow_radius = entity_radius + 3;
            Color glow_color = {entity_color.r, entity_color.g, entity_color.b, 80};
            DrawCircle(x, y, glow_radius, glow_color);
            
            // Draw main entity circle
            DrawCircle(x, y, entity_radius, entity_color);
            DrawCircleLines(x, y, entity_radius, BLACK);
            
            // Draw white background for symbol visibility
            float symbol_bg_radius = entity_radius * 0.7f;
            DrawCircle(x, y, symbol_bg_radius, {255, 255, 255, 200});
            
            // Draw entity symbol based on type
            int codepoint = get_entity_codepoint(static_cast<EntityType>(entity.entity_type));
            if (tile_size > 15) {
                int font_size = static_cast<int>(tile_size * 0.3f);
                font_size = std::max(10, std::min(font_size, 20));
                
                // Get glyph info for positioning
                int utf8Size;
                const char* utf8_text = CodepointToUTF8(codepoint, &utf8Size);
                Vector2 glyph_size = MeasureTextEx(GetFontDefault(), utf8_text, font_size, 1);
                float text_x = x - glyph_size.x / 2;
                float text_y = y - glyph_size.y / 2;
                
                // Draw symbol with shadow for visibility
                DrawTextCodepoint(GetFontDefault(), codepoint, {text_x + 1, text_y + 1}, font_size, DARKGRAY);
                DrawTextCodepoint(GetFontDefault(), codepoint, {text_x, text_y}, font_size, BLACK);
            }
        }
        
        // Draw general name above sprite (generals only, when zoomed in enough
        // to read it — tile_size is constant, so gate on on-screen size)
        if (entity.entity_type == 0 && tile_size * camera.zoom > 26) {
            std::string name_str(entity.name.data());
            if (!name_str.empty()) {
                int name_font_size = std::max(7, std::min(10, (int)(tile_size * 0.13f)));
                Vector2 name_size = MeasureTextEx(GetFontDefault(), name_str.c_str(), name_font_size, 1);
                float name_x = x - name_size.x / 2;
                float name_y = y - entity_radius - name_size.y - 2;
                DrawRectangle((int)(name_x - 2), (int)(name_y - 1),
                              (int)(name_size.x + 4), (int)(name_size.y + 2), {0, 0, 0, 160});
                DrawTextEx(GetFontDefault(), name_str.c_str(), {name_x, name_y},
                           name_font_size, 1, WHITE);
            }
        }

        // Draw morale & supply bars for generals (tile large enough)
        if (entity.entity_type == 0 && tile_size > 28) {
            float bar_w = tile_size * 0.55f;
            float bar_h = 3.0f;
            float bar_x = x - bar_w / 2;
            float bar_y = y + entity_radius + 3;
            // Morale bar (blue)
            DrawRectangle((int)bar_x - 1, (int)bar_y - 1, (int)bar_w + 2, (int)bar_h + 2, {0,0,0,140});
            float morale_fill = (entity.morale / 100.0f) * bar_w;
            Color morale_color = entity.morale > 60 ? Color{30,144,255,220} :
                                 entity.morale > 30 ? Color{255,165,0,220} : Color{220,20,60,220};
            DrawRectangle((int)bar_x, (int)bar_y, (int)morale_fill, (int)bar_h, morale_color);
            // Supply bar (green) — one pixel below
            float sup_y = bar_y + bar_h + 2;
            DrawRectangle((int)bar_x - 1, (int)sup_y - 1, (int)bar_w + 2, (int)bar_h + 2, {0,0,0,140});
            float sup_fill = (entity.supplies / 100.0f) * bar_w;
            Color sup_color = entity.supplies > 60 ? Color{50,205,50,220} :
                              entity.supplies > 25 ? Color{255,165,0,220} : Color{220,20,60,220};
            DrawRectangle((int)bar_x, (int)sup_y, (int)sup_fill, (int)bar_h, sup_color);
        }

        // Draw troop count if it's a military unit and tile is large enough
        if (entity.assigned_soldiers > 0 && tile_size > 25) {
            std::string troop_text = std::to_string(entity.assigned_soldiers);
            int troop_font_size = static_cast<int>(tile_size * 0.15f);
            troop_font_size = std::max(8, std::min(troop_font_size, 12));
            
            Vector2 troop_size = MeasureTextEx(GetFontDefault(), troop_text.c_str(), troop_font_size, 1);
            float troop_x = x - troop_size.x / 2;
            float troop_y = y + entity_radius + 2; // Position below entity
            
            // Draw background for troop count
            DrawRectangle(troop_x - 2, troop_y - 1, troop_size.x + 4, troop_size.y + 2, {0, 0, 0, 150});
            DrawTextEx(GetFontDefault(), troop_text.c_str(), {troop_x, troop_y}, troop_font_size, 1, WHITE);
        }
   }

   int get_entity_codepoint(EntityType entity_type) {
        switch (entity_type) {
            case EntityType::GENERAL: return 0x2694;    // ⚔ Crossed Swords
            case EntityType::SCOUT: return 0x1F441;     // 👁 Eye
            case EntityType::ARMY: return 0x1F6E1;      // 🛡 Shield
            case EntityType::MERCHANT: return 0x1F4B0;  // 💰 Money Bag
            case EntityType::CARAVAN: return 0x1F69A;   // 🚚 Delivery Truck
            default: return 0x25CF;                     // ● Black Circle
        }
   }

   std::pair<float, float> get_tile_position_from_coords(int q, int r) {
        float x = center_x + (q * hex_width);
        float y = center_y + (r * hex_height * 2) + (q * hex_height);
        return {x, y};
   }

   // City name parsing functions
   std::string extract_city_name(const std::string& owner_field) {
        if (owner_field.find("CITY:") == 0) {
            size_t start = 5; // Skip "CITY:"
            size_t end = owner_field.find('#');
            if (end != std::string::npos) {
                return owner_field.substr(start, end - start);
            }
        }
        return "";
   }

   std::string extract_original_owner(const std::string& owner_field) {
        if (owner_field.find("CITY:") == 0) {
            size_t hash_pos = owner_field.find('#');
            if (hash_pos != std::string::npos) {
                return owner_field.substr(hash_pos + 1);
            }
        }
        return owner_field;
   }

   bool has_encoded_city_name(const std::string& owner_field) {
        return owner_field.find("CITY:") == 0;
   }
   
   // Entity helper functions
   std::vector<PositionedEntity*> find_entities_at_tile(int q, int r, PositionedEntity* entity_data, int num_entities) {
        std::vector<PositionedEntity*> entities_on_tile;
        if (!entity_data) return entities_on_tile;
        
        for (int i = 0; i < num_entities; ++i) {
            PositionedEntity* entity = &entity_data[i];
            if (entity->q == q && entity->r == r && 
                strlen(entity->name.data()) > 0) { // Valid entity with name
                entities_on_tile.push_back(entity);
            }
        }
        return entities_on_tile;
   }
   
   std::string get_entity_type_name(EntityType entity_type) {
        switch (entity_type) {
            case EntityType::GENERAL: return "General";
            case EntityType::SCOUT: return "Scout";
            case EntityType::ARMY: return "Army";
            case EntityType::MERCHANT: return "Merchant";
            case EntityType::CARAVAN: return "Trade Caravan";
            default: return "Unknown";
        }
   }

private:

    std::pair<float, float> get_tile_position(const HexTile& tile) {
        float x = center_x + (tile.q * hex_width);
        float y = center_y + (tile.r * hex_height * 2) + (tile.q * hex_height);
        return {x, y};
    }

    void on_mouse_hover(const std::unordered_map<std::pair<int, int>, HexTile*>& shared_tile_map, PositionedEntity* entity_data, int num_entities) {
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

    void draw_tile_info(HexTile* tile, PositionedEntity* entity_data, int num_entities) {
        std::string owner_field = std::string(tile->owner.data());
        
        // Find entities on this tile
        std::vector<PositionedEntity*> entities_on_tile = find_entities_at_tile(tile->q, tile->r, entity_data, num_entities);
        
        // Panel dimensions and styling - adjust height based on content
        int panel_width = 200;
        int base_panel_height = 120;
        int entity_info_height = entities_on_tile.size() * 24; // 24 pixels per entity (2 lines)
        int panel_height = base_panel_height + entity_info_height;
        int panel_x = width - panel_width - 10; // Right side of screen
        int panel_y = height - panel_height - 40; // Bottom right
        int header_font_size = 11;
        int body_font_size = 9;
        
        // Background panel
        Color panel_bg = {50, 50, 50, 200}; // Dark semi-transparent
        Color panel_border = {100, 100, 100, 255}; // Gray border
        DrawRectangle(panel_x, panel_y, panel_width, panel_height, panel_bg);
        DrawRectangleLines(panel_x, panel_y, panel_width, panel_height, panel_border);
        
        // Header
        std::string header = "Tile (" + std::to_string(tile->q) + ", " + std::to_string(tile->r) + ")";
        DrawRectangle(panel_x, panel_y, panel_width, 20, panel_border);
        DrawTextEx(GetFontDefault(), header.c_str(), {(float)(panel_x + 8), (float)(panel_y + 4)}, header_font_size, 1, WHITE);
        
        int text_y = panel_y + 25;
        int line_height = 12;
        
        // Basic info
        std::string terrain = "Terrain: " + hex_tile_type_to_string[tile->terrain_type];
        DrawTextEx(GetFontDefault(), terrain.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, WHITE);
        text_y += line_height;
        
        // Environmental stats (abbreviated for space)
        std::string env_stats = "E:" + std::to_string(static_cast<int>(tile->elevation * 100)) + 
                               " T:" + std::to_string(static_cast<int>(tile->temperature * 100)) +
                               " M:" + std::to_string(static_cast<int>(tile->moisture * 100));
        DrawTextEx(GetFontDefault(), env_stats.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, LIGHTGRAY);
        text_y += line_height;
        
        // Resource outputs
        std::string resources = "Resources: F:" + std::to_string(static_cast<int>(tile->food_output)) +
                               " M:" + std::to_string(static_cast<int>(tile->material_output)) +
                               " I:" + std::to_string(static_cast<int>(get_base_metal_output(*tile)));
        DrawTextEx(GetFontDefault(), resources.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, WHITE);
        text_y += line_height;
        
        std::string pop_cap = "Pop Cap: " + std::to_string(tile->population_capacity);
        DrawTextEx(GetFontDefault(), pop_cap.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, WHITE);
        text_y += line_height + 3;
        
        // Owner and city information
        // Only show city name if this tile actually has a city (population_capacity >= 1000)
        CityInfo city = get_city_info(*tile);
        if (city.type != CityType::NONE && has_encoded_city_name(owner_field)) {
            std::string city_name = extract_city_name(owner_field);
            if (!city_name.empty()) {
                DrawTextEx(GetFontDefault(), ("City: " + city_name).c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, YELLOW);
                text_y += line_height;
            }
        }
        
        // Always show owner (extract from city encoding if present)
        if (has_encoded_city_name(owner_field)) {
            std::string original_owner = extract_original_owner(owner_field);
            if (!original_owner.empty() && original_owner != "None") {
                DrawTextEx(GetFontDefault(), ("Owner: " + original_owner).c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, SKYBLUE);
                text_y += line_height;
            }
        } else if (owner_field.find("PENDING:") == 0) {
            // Pending outpost — extract owner after '#' or show as under construction
            size_t hash_pos = owner_field.find('#');
            std::string pending_owner = (hash_pos != std::string::npos)
                ? owner_field.substr(hash_pos + 1) : "";
            DrawTextEx(GetFontDefault(), "Construction in progress", {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, {255, 220, 0, 255});
            text_y += line_height;
            if (!pending_owner.empty() && pending_owner != "None") {
                DrawTextEx(GetFontDefault(), ("Owner: " + pending_owner).c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, SKYBLUE);
                text_y += line_height;
            }
        } else if (owner_field != "None") {
            DrawTextEx(GetFontDefault(), ("Owner: " + owner_field).c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, SKYBLUE);
            text_y += line_height;
        }
        
        // Special resource information
        if (has_special_resource(*tile)) {
            ResourceNodeType resource_type = get_resource_node_type(*tile);
            std::string resource_name;
            Color resource_color = YELLOW;
            switch (resource_type) {
                case ResourceNodeType::GOLD_MINE: resource_name = "Gold Mine"; resource_color = YELLOW; break;
                case ResourceNodeType::IRON_DEPOSIT: resource_name = "Iron Deposit"; resource_color = GRAY; break;
                case ResourceNodeType::STONE_QUARRY: resource_name = "Stone Quarry"; resource_color = BROWN; break;
                case ResourceNodeType::RARE_HERBS: resource_name = "Rare Herbs"; resource_color = GREEN; break;
                default: resource_name = "Unknown Resource"; break;
            }
            DrawTextEx(GetFontDefault(), ("Special: " + resource_name).c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, resource_color);
            text_y += line_height;
        }
        
        // City type information (using city variable declared above)
        if (city.type != CityType::NONE) {
            std::string city_type_name = get_city_type_name(city.type);
            std::string development_name = get_city_development_name(city.development_level);
            DrawTextEx(GetFontDefault(), (city_type_name + " (" + development_name + ")").c_str(), 
                      {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, ORANGE);
            text_y += line_height;
        }
        
        // Entity information
        if (!entities_on_tile.empty()) {
            text_y += 3; // Small gap before entity section
            
            // Entity section header
            DrawTextEx(GetFontDefault(), "Entities:", {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, LIGHTGRAY);
            text_y += line_height;
            
            for (PositionedEntity* entity : entities_on_tile) {
                // Entity type and name
                std::string entity_name = std::string(entity->name.data());
                std::string entity_type = get_entity_type_name(static_cast<EntityType>(entity->entity_type));
                std::string entity_house = std::string(entity->house_name.data());
                
                // Main entity info line
                std::string entity_info = entity_type + ": " + entity_name;
                Color entity_color = {entity->color[0], entity->color[1], entity->color[2], 255};
                DrawTextEx(GetFontDefault(), entity_info.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, entity_color);
                text_y += line_height;
                
                // Additional info line (house and military strength if applicable)
                std::string additional_info = "House: " + entity_house;
                if (entity->assigned_soldiers > 0) {
                    additional_info += " | Troops: " + std::to_string(entity->assigned_soldiers);
                }
                DrawTextEx(GetFontDefault(), additional_info.c_str(), {(float)(panel_x + 12), (float)text_y}, body_font_size - 1, 1, LIGHTGRAY);
                text_y += line_height;
            }
        }
    }

    // ── Minimap ───────────────────────────────────────────────────────────────

    void draw_minimap(HexTile* tile_data, int num_tiles) {
        if (!show_minimap) return;

        const int MM_W = 160, MM_H = 120, MM_MARGIN = 10;
        const int MM_X = width - MM_W - MM_MARGIN;
        // Sit above tile info panel (base height ~120) + margin
        const int MM_Y = height - MM_H - 200;

        // Compute bounds once
        if (!mm_bounds_computed && num_tiles > 0) {
            mm_min_q = mm_max_q = tile_data[0].q;
            mm_min_r = mm_max_r = tile_data[0].r;
            for (int i = 1; i < num_tiles; ++i) {
                if (tile_data[i].q < mm_min_q) mm_min_q = tile_data[i].q;
                if (tile_data[i].q > mm_max_q) mm_max_q = tile_data[i].q;
                if (tile_data[i].r < mm_min_r) mm_min_r = tile_data[i].r;
                if (tile_data[i].r > mm_max_r) mm_max_r = tile_data[i].r;
            }
            mm_bounds_computed = true;
        }
        if (!mm_bounds_computed) return;

        int qrange = mm_max_q - mm_min_q + 1;
        int rrange = mm_max_r - mm_min_r + 1;

        // Panel background
        DrawRectangle(MM_X - 2, MM_Y - 2, MM_W + 4, MM_H + 4, {0, 0, 0, 200});
        DrawRectangleLines(MM_X - 2, MM_Y - 2, MM_W + 4, MM_H + 4, {120, 120, 120, 200});

        // Draw each tile as a 1-2px rectangle
        for (int i = 0; i < num_tiles; ++i) {
            HexTile* t = &tile_data[i];
            float nx = (float)(t->q - mm_min_q) / qrange;
            float ny = (float)(t->r - mm_min_r) / rrange;
            int px = MM_X + (int)(nx * MM_W);
            int py = MM_Y + (int)(ny * MM_H);

            Color col;
            bool owned = (t->owner_color[3] > 10);
            if (owned) {
                col = {t->owner_color[0], t->owner_color[1], t->owner_color[2], 200};
            } else {
                col = terrain_colors.count(t->terrain_type)
                      ? terrain_colors[t->terrain_type] : Color{80, 80, 80, 255};
                col.a = 160;
            }
            DrawRectangle(px, py, 2, 2, col);
        }

        // Entity dots
        if (current_entity_data) {
            for (int i = 0; i < current_num_entities; ++i) {
                PositionedEntity* e = &current_entity_data[i];
                if (strlen(e->name.data()) == 0 || std::string(e->name.data()).find("__") == 0)
                    continue;
                float nx = (float)(e->q - mm_min_q) / qrange;
                float ny = (float)(e->r - mm_min_r) / rrange;
                int px = MM_X + (int)(nx * MM_W);
                int py = MM_Y + (int)(ny * MM_H);
                Color ec = {e->color[0], e->color[1], e->color[2], 255};
                DrawRectangle(px - 1, py - 1, 3, 3, ec);
            }
        }

        // Viewport rectangle
        Vector2 tl_world = GetScreenToWorld2D({0.0f, 0.0f}, camera);
        Vector2 br_world = GetScreenToWorld2D({(float)width, (float)height}, camera);
        auto world_to_mm = [&](float wx, float wy) -> std::pair<int,int> {
            // Invert hex_to_pixel: wx = center_x + q*hex_width  →  q ≈ (wx - center_x) / hex_width
            float q_f = (wx - center_x) / hex_width;
            float r_f = (wy - center_y - q_f * hex_height) / (hex_height * 2.0f);
            float nx = (q_f - mm_min_q) / qrange;
            float ny = (r_f - mm_min_r) / rrange;
            return {MM_X + (int)(nx * MM_W), MM_Y + (int)(ny * MM_H)};
        };
        auto [vx1, vy1] = world_to_mm(tl_world.x, tl_world.y);
        auto [vx2, vy2] = world_to_mm(br_world.x, br_world.y);
        vx1 = std::max(MM_X, std::min(MM_X + MM_W, vx1));
        vy1 = std::max(MM_Y, std::min(MM_Y + MM_H, vy1));
        vx2 = std::max(MM_X, std::min(MM_X + MM_W, vx2));
        vy2 = std::max(MM_Y, std::min(MM_Y + MM_H, vy2));
        DrawRectangleLines(vx1, vy1, vx2 - vx1, vy2 - vy1, {255, 255, 255, 200});

        // Label
        DrawTextEx(GetFontDefault(), "Map [M]", {(float)(MM_X), (float)(MM_Y - 12)}, 9, 1, LIGHTGRAY);
    }

    // ── Event Log Panel ───────────────────────────────────────────────────────

    // ── Agent inspector helpers ─────────────────────────────────────────────

    static std::string shm_str(const char* p, int max_len) {
        return std::string(p, strnlen(p, max_len));
    }

    // Word-wrap a single logical line into display lines fitting max_w
    std::vector<std::string> wrap_line(const std::string& text, float max_w, int font_size) {
        std::vector<std::string> out;
        std::istringstream iss(text);
        std::string word, line;
        while (std::getline(iss, word, ' ')) {
            std::string candidate = line.empty() ? word : line + " " + word;
            if (!line.empty() &&
                MeasureTextEx(GetFontDefault(), candidate.c_str(), font_size, 1).x > max_w) {
                out.push_back(line);
                line = word;
            } else {
                line = candidate;
            }
        }
        out.push_back(line);  // keeps empty lines as paragraph breaks
        return out;
    }

    // Color a chat transcript line by its role prefix
    Color chat_line_color(const std::string& line, Color agent_color) {
        if (line.rfind("── GAME MASTER", 0) == 0) return {120, 200, 255, 255};
        if (line.rfind("── ", 0) == 0) return agent_color;
        if (line.rfind("→ ", 0) == 0) return {255, 220, 120, 255};
        if (line.find("↳") != std::string::npos) return {160, 160, 160, 255};
        if (line.rfind("💭", 0) == 0) return {200, 160, 255, 255};
        if (line.rfind("…", 0) == 0) return {110, 110, 110, 255};
        return {232, 232, 232, 255};
    }

    // ── Turn stats panel ('Y', default on) ────────────────────────────────────

    void draw_turn_stats_panel(House* house_data, int num_houses,
                               PositionedEntity* entity_data, int num_entities) {
        if (!show_turn_stats) return;

        const int PANEL_W = 250;
        const int PANEL_X = width - PANEL_W - 10;
        int y = 70;

        // Header clock from agent inspector shm
        int turn = 0, year = 1, season_idx = 0, phase_idx = 0, step_count = 0;
        bool have_clock = false;
        if (agents_raw != MAP_FAILED) {
            const char* base = static_cast<const char*>(agents_raw);
            turn = *reinterpret_cast<const int*>(base + 4);
            year = *reinterpret_cast<const int*>(base + 8);
            season_idx = std::max(0, std::min(3, *reinterpret_cast<const int*>(base + 12)));
            phase_idx = std::max(0, std::min(3, *reinterpret_cast<const int*>(base + 16)));
            step_count = *reinterpret_cast<const int*>(base + 20);
            have_clock = true;
        }
        const char* season_names[4] = {"Spring", "Summer", "Autumn", "Winter"};
        const Color season_colors[4] = {{100,200,100,255},{255,200,50,255},{210,120,30,255},{180,220,255,255}};
        const char* phase_names[4] = {"Production", "Actions", "Events", "Cleanup"};

        int house_block = 66;
        int header_h = have_clock ? 66 : 24;
        int entities_h = 20;
        int panel_h = header_h + 6 + num_houses * house_block + entities_h + 10;

        DrawRectangle(PANEL_X, y, PANEL_W, panel_h, {10, 10, 30, 225});
        DrawRectangleLines(PANEL_X, y, PANEL_W, panel_h, {120, 120, 180, 255});
        DrawRectangle(PANEL_X, y, PANEL_W, 20, {30, 30, 80, 255});
        DrawTextEx(GetFontDefault(), "Realm Status [Y]",
                   {(float)(PANEL_X + 6), (float)(y + 4)}, 10, 1, WHITE);
        y += 24;

        if (have_clock) {
            std::string l1 = std::string("Year ") + std::to_string(year) + "  ·  " +
                             season_names[season_idx] + "  ·  Week " + std::to_string(turn);
            DrawTextEx(GetFontDefault(), l1.c_str(), {(float)(PANEL_X + 8), (float)y},
                       11, 1, season_colors[season_idx]);
            y += 15;
            std::string l2 = std::string(phase_names[phase_idx]) + " phase  ·  step " +
                             std::to_string(step_count);
            DrawTextEx(GetFontDefault(), l2.c_str(), {(float)(PANEL_X + 8), (float)y},
                       9, 1, LIGHTGRAY);
            y += 16;
            DrawLine(PANEL_X + 6, y, PANEL_X + PANEL_W - 6, y, {60, 60, 100, 255});
            y += 8;
        }

        if (house_data) {
            for (int hi = 0; hi < num_houses; ++hi) {
                House* h = &house_data[hi];
                std::string hname = shm_str(h->name.data(), 50);
                if (hname.empty() || hname == "None") continue;
                Color hcol = {h->color[0], h->color[1], h->color[2], 255};

                DrawRectangle(PANEL_X + 8, y + 2, 10, 10, hcol);
                DrawTextEx(GetFontDefault(), hname.c_str(),
                           {(float)(PANEL_X + 22), (float)y}, 11, 1, hcol);
                if (h->at_war > 0) {
                    std::string war = "⚔ " + std::to_string(h->at_war);
                    DrawTextEx(GetFontDefault(), war.c_str(),
                               {(float)(PANEL_X + PANEL_W - 40), (float)y}, 10, 1, RED);
                }
                y += 15;

                char buf[128];
                snprintf(buf, sizeof(buf), "F %-5.0f M %-5.0f Fe %-5.0f Au %-5.0f",
                         h->food, h->material, h->metal, h->gold);
                DrawTextEx(GetFontDefault(), buf, {(float)(PANEL_X + 12), (float)y}, 9, 1,
                           {220, 220, 220, 255});
                y += 13;
                snprintf(buf, sizeof(buf), "Pop %-5d Loy %-4d Mil %-5d ravens %d",
                         h->population, h->population_loyalty, h->military_power,
                         h->ravens_in_transit);
                DrawTextEx(GetFontDefault(), buf, {(float)(PANEL_X + 12), (float)y}, 9, 1,
                           {180, 180, 200, 255});
                y += 14;
                DrawLine(PANEL_X + 6, y, PANEL_X + PANEL_W - 6, y, {45, 45, 70, 255});
                y += 9;
            }
        }

        if (entity_data && num_entities > 0) {
            int generals = 0, caravans = 0;
            for (int i = 0; i < num_entities; ++i) {
                PositionedEntity* e = &entity_data[i];
                std::string n = shm_str(e->name.data(), 50);
                if (n.empty() || n.rfind("__", 0) == 0) continue;
                if (e->entity_type == 0) generals++;
                else if (e->entity_type == 4) caravans++;
            }
            char buf[64];
            snprintf(buf, sizeof(buf), "Generals %d   Caravans %d", generals, caravans);
            DrawTextEx(GetFontDefault(), buf, {(float)(PANEL_X + 8), (float)y}, 9, 1,
                       {200, 200, 160, 255});
        }
    }

    // ── Agent chat inspector ('C') ────────────────────────────────────────────

    void draw_chat_inspector() {
        if (!show_chat || agents_raw == MAP_FAILED) return;

        const char* base = static_cast<const char*>(agents_raw);
        int num_agents = *reinterpret_cast<const int*>(base + 0);
        int write_seq = *reinterpret_cast<const int*>(base + 24);

        int px = width / 20, py = height / 20;
        int pw = width - 2 * px, ph = height - 2 * py;

        DrawRectangle(px, py, pw, ph, {8, 8, 22, 245});
        DrawRectangleLines(px, py, pw, ph, {120, 120, 180, 255});
        DrawRectangle(px, py, pw, 24, {30, 30, 80, 255});
        DrawTextEx(GetFontDefault(),
                   "Agent Chat [C]   up/down select   PgUp/PgDn/wheel scroll   End latest   ESC close",
                   {(float)(px + 8), (float)(py + 7)}, 10, 1, WHITE);

        if (num_agents <= 0) {
            DrawTextEx(GetFontDefault(), "No agents reporting yet.",
                       {(float)(px + 20), (float)(py + 50)}, 12, 1, LIGHTGRAY);
            return;
        }
        if (chat_agent_index >= num_agents) chat_agent_index = num_agents - 1;
        if (chat_agent_index < 0) chat_agent_index = 0;

        // Left: agent list
        const int LIST_W = 240;
        int ly = py + 34;
        for (int i = 0; i < num_agents; ++i) {
            const char* slot = base + AGENTS_HEADER + i * AGENT_SLOT;
            std::string aname = shm_str(slot + AO_NAME, 64);
            std::string kind = shm_str(slot + AO_KIND, 16);
            const unsigned char* col = reinterpret_cast<const unsigned char*>(slot + AO_COLOR);
            Color agent_col = {col[0], col[1], col[2], 255};

            if (i == chat_agent_index)
                DrawRectangle(px + 4, ly - 2, LIST_W - 8, 32, {40, 40, 90, 255});
            DrawRectangle(px + 10, ly + 4, 10, 10, agent_col);
            std::string display = aname.size() > 24 ? aname.substr(0, 23) + "..." : aname;
            DrawTextEx(GetFontDefault(), display.c_str(), {(float)(px + 26), (float)ly},
                       10, 1, i == chat_agent_index ? WHITE : LIGHTGRAY);
            DrawTextEx(GetFontDefault(), kind.c_str(), {(float)(px + 26), (float)(ly + 13)},
                       8, 1, {140, 140, 160, 255});
            ly += 34;
            if (ly > py + ph - 20) break;
        }

        DrawLine(px + LIST_W, py + 24, px + LIST_W, py + ph - 4, {60, 60, 100, 255});

        // Right: selected agent detail
        const char* slot = base + AGENTS_HEADER + chat_agent_index * AGENT_SLOT;
        std::string aname = shm_str(slot + AO_NAME, 64);
        std::string kind = shm_str(slot + AO_KIND, 16);
        std::string house = shm_str(slot + AO_HOUSE, 50);
        std::string status = shm_str(slot + AO_STATUS, 256);
        std::string objectives = shm_str(slot + AO_OBJECTIVES, 512);
        int chat_len = *reinterpret_cast<const int*>(slot + AO_CHAT_LEN);
        chat_len = std::max(0, std::min(AGENT_CHAT_MAX - 1, chat_len));
        std::string chat(slot + AO_CHAT, chat_len);
        const unsigned char* col = reinterpret_cast<const unsigned char*>(slot + AO_COLOR);
        Color agent_col = {col[0], col[1], col[2], 255};

        int rx = px + LIST_W + 12;
        int ry = py + 34;
        int rw = px + pw - 12 - rx;

        std::string title = aname + (house.empty() ? "" : "  ·  " + house) +
                            (kind.empty() ? "" : "  (" + kind + ")");
        DrawTextEx(GetFontDefault(), title.c_str(), {(float)rx, (float)ry}, 13, 1, agent_col);
        ry += 20;
        if (!status.empty()) {
            DrawTextEx(GetFontDefault(), status.c_str(), {(float)rx, (float)ry}, 9, 1,
                       {200, 200, 160, 255});
            ry += 14;
        }
        if (!objectives.empty()) {
            std::istringstream iss(objectives);
            std::string obj;
            DrawTextEx(GetFontDefault(), "Objectives:", {(float)rx, (float)ry}, 9, 1,
                       {150, 200, 150, 255});
            ry += 12;
            while (std::getline(iss, obj) && ry < py + ph - 60) {
                if (obj.empty()) continue;
                std::string line = "  - " + obj;
                DrawTextEx(GetFontDefault(), line.c_str(), {(float)rx, (float)ry}, 9, 1,
                           {170, 210, 170, 255});
                ry += 12;
            }
        }
        ry += 4;
        DrawLine(rx, ry, px + pw - 12, ry, {60, 60, 100, 255});
        ry += 6;

        // Chat transcript: wrap, then draw the scrolled visible slice
        const int FONT = 10, LINE_H = FONT + 3;
        std::vector<std::pair<std::string, Color>> wrapped;
        {
            std::istringstream iss(chat);
            std::string raw_line;
            while (std::getline(iss, raw_line)) {
                Color c = chat_line_color(raw_line, agent_col);
                for (auto& l : wrap_line(raw_line, (float)rw, FONT))
                    wrapped.emplace_back(l, c);
            }
        }

        int visible = (py + ph - 12 - ry) / LINE_H;
        int total = (int)wrapped.size();
        int max_scroll = std::max(0, total - visible);

        // Auto-follow newest when Python writes a new snapshot
        if (write_seq != agents_last_seq) {
            agents_last_seq = write_seq;
            if (chat_follow) chat_scroll = max_scroll;
        }
        if (chat_follow) chat_scroll = max_scroll;
        chat_scroll = std::max(0, std::min(chat_scroll, max_scroll));

        BeginScissorMode(rx, ry, rw, py + ph - 12 - ry);
        for (int i = 0; i < visible && (chat_scroll + i) < total; ++i) {
            auto& entry = wrapped[chat_scroll + i];
            DrawTextEx(GetFontDefault(), entry.first.c_str(),
                       {(float)rx, (float)(ry + i * LINE_H)}, FONT, 1, entry.second);
        }
        EndScissorMode();

        // Scrollbar
        if (total > visible && max_scroll > 0) {
            int track_h = py + ph - 12 - ry;
            float frac = (float)visible / total;
            int bar_h = std::max(20, (int)(track_h * frac));
            int bar_y = ry + (int)((track_h - bar_h) * ((float)chat_scroll / max_scroll));
            DrawRectangle(px + pw - 8, ry, 4, track_h, {30, 30, 50, 255});
            DrawRectangle(px + pw - 8, bar_y, 4, bar_h, {120, 120, 180, 255});
        }
    }

    void draw_event_log_panel() {
        if (!show_event_log || events_raw == MAP_FAILED) return;

        const int PANEL_W = 230, LINE_H = 13, SHOW_N = 8;
        const int PANEL_H = SHOW_N * LINE_H + 30;
        const int PANEL_X = width - PANEL_W - 10;
        const int PANEL_Y = 60;  // Below entity inspector header area

        DrawRectangle(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, {10, 10, 30, 225});
        DrawRectangleLines(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, {120, 120, 180, 255});
        DrawRectangle(PANEL_X, PANEL_Y, PANEL_W, 20, {30, 30, 80, 255});
        DrawTextEx(GetFontDefault(), "Event Log [L]",
                   {(float)(PANEL_X + 6), (float)(PANEL_Y + 4)}, 10, 1, WHITE);

        int head = *static_cast<int*>(events_raw);
        const char* events_base = static_cast<char*>(events_raw) + 4;

        int y = PANEL_Y + 24;
        for (int i = 0; i < SHOW_N; ++i) {
            int idx = ((head - 1 - i) + EVENTS_MAX) % EVENTS_MAX;
            const char* entry = events_base + idx * EVENT_STR_SIZE;
            if (entry[0] == '\0') continue;
            std::string line(entry, strnlen(entry, EVENT_STR_SIZE - 1));
            if (line.size() > 44) line = line.substr(0, 43) + "...";
            Color lc = (i == 0) ? WHITE : LIGHTGRAY;
            DrawTextEx(GetFontDefault(), line.c_str(),
                       {(float)(PANEL_X + 5), (float)y}, 9, 1, lc);
            y += LINE_H;
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    void draw_stat_bar(int x, int y, int bar_w, int bar_h, int value,
                       Color filled_col, Color bg_col) {
        DrawRectangle(x, y, bar_w, bar_h, bg_col);
        int filled = (int)(bar_w * std::min(100, std::max(0, value)) / 100.0f);
        if (filled > 0) DrawRectangle(x, y, filled, bar_h, filled_col);
        DrawRectangleLines(x, y, bar_w, bar_h, {100, 100, 100, 180});
    }

    void draw_wrapped_text(int x, int& y, int max_w, const std::string& text,
                           int font_size, Color col) {
        // Simple word-wrap: split on spaces, accumulate until line exceeds max_w
        std::istringstream iss(text);
        std::string word, line;
        while (std::getline(iss, word, ' ')) {
            std::string candidate = line.empty() ? word : line + " " + word;
            if (MeasureTextEx(GetFontDefault(), candidate.c_str(), font_size, 1).x > max_w && !line.empty()) {
                DrawTextEx(GetFontDefault(), line.c_str(), {(float)x, (float)y}, font_size, 1, col);
                y += font_size + 2;
                line = word;
            } else {
                line = candidate;
            }
        }
        if (!line.empty()) {
            DrawTextEx(GetFontDefault(), line.c_str(), {(float)x, (float)y}, font_size, 1, col);
            y += font_size + 2;
        }
    }

    // ── Entity click-select ───────────────────────────────────────────────────

    void check_entity_click(float mouse_x, float mouse_y,
                             const std::unordered_map<std::pair<int,int>, HexTile*>& shared_tile_map) {
        if (!current_entity_data) { selected_entity_index = -1; return; }

        auto tile_opt = get_tile_at_position((int)mouse_x, (int)mouse_y, shared_tile_map);
        if (!tile_opt) { selected_entity_index = -1; return; }

        int tq = (*tile_opt)->q, tr = (*tile_opt)->r;
        std::vector<int> indices;
        for (int i = 0; i < current_num_entities; ++i) {
            PositionedEntity* e = &current_entity_data[i];
            if (e->q == tq && e->r == tr && strlen(e->name.data()) > 0 &&
                std::string(e->name.data()).find("__") != 0) {
                indices.push_back(i);
            }
        }
        if (indices.empty()) { selected_entity_index = -1; return; }

        // Cycle through entities on the same tile on repeated clicks
        auto it = std::find(indices.begin(), indices.end(), selected_entity_index);
        if (it != indices.end()) {
            ++it;
            selected_entity_index = (it != indices.end()) ? *it : indices[0];
        } else {
            selected_entity_index = indices[0];
        }
    }

    // ── Entity Inspector Panel ────────────────────────────────────────────────

    void draw_entity_inspector() {
        if (selected_entity_index < 0 || !current_entity_data) return;
        if (selected_entity_index >= current_num_entities) {
            selected_entity_index = -1; return;
        }
        PositionedEntity* e = &current_entity_data[selected_entity_index];
        if (strlen(e->name.data()) == 0) { selected_entity_index = -1; return; }

        std::string name      = std::string(e->name.data());
        std::string house     = std::string(e->house_name.data());
        std::string orders_s  = std::string(e->orders.data());
        std::string type_name = get_entity_type_name(static_cast<EntityType>(e->entity_type));
        Color ec = {e->color[0], e->color[1], e->color[2], 255};

        int panel_w = 240;
        int panel_x = width - panel_w - 10;
        int panel_y = 10;

        // Estimate height
        int orders_h = 0;
        if (!orders_s.empty()) {
            int chars_per_line = std::max(1, (panel_w - 16) / 6);
            orders_h = ((int)orders_s.size() / chars_per_line + 2) * 13 + 18;
        }
        bool has_soldiers = (e->assigned_soldiers > 0);
        int panel_h = 200 + (has_soldiers ? 14 : 0) + orders_h;

        Color bg     = {15, 15, 35, 225};
        Color border = {ec.r, ec.g, ec.b, 200};
        DrawRectangle(panel_x, panel_y, panel_w, panel_h, bg);
        DrawRectangleLines(panel_x, panel_y, panel_w, panel_h, border);

        // Header bar
        Color hdr_bg = {(unsigned char)(ec.r/3), (unsigned char)(ec.g/3), (unsigned char)(ec.b/3), 255};
        DrawRectangle(panel_x, panel_y, panel_w, 22, hdr_bg);
        DrawTextEx(GetFontDefault(), (type_name + ": " + name).c_str(),
                   {(float)(panel_x + 6), (float)(panel_y + 5)}, 11, 1, WHITE);
        DrawTextEx(GetFontDefault(), "[ESC]",
                   {(float)(panel_x + panel_w - 40), (float)(panel_y + 6)}, 9, 1, LIGHTGRAY);

        int y   = panel_y + 28;
        int lh  = 14;
        int fs  = 10;
        int ix  = panel_x + 8;
        int bar_w = panel_w - 16;

        DrawTextEx(GetFontDefault(), ("House: " + house).c_str(), {(float)ix, (float)y}, fs, 1, ec); y += lh;
        std::string pos_str = "Position: (" + std::to_string(e->q) + ", " + std::to_string(e->r) + ")";
        DrawTextEx(GetFontDefault(), pos_str.c_str(), {(float)ix, (float)y}, fs, 1, WHITE); y += lh;

        if (has_soldiers) {
            DrawTextEx(GetFontDefault(), ("Soldiers: " + std::to_string(e->assigned_soldiers)).c_str(),
                       {(float)ix, (float)y}, fs, 1, WHITE); y += lh;
        }

        y += 4;

        // Equipment bar
        DrawTextEx(GetFontDefault(), "Equipment:", {(float)ix, (float)y}, fs, 1, LIGHTGRAY); y += lh;
        draw_stat_bar(ix, y, bar_w, 8, e->equipment_level, {200, 160, 50, 255}, {50, 40, 10, 255});
        DrawTextEx(GetFontDefault(), (std::to_string(e->equipment_level) + "%").c_str(),
                   {(float)(panel_x + panel_w - 32), (float)(y - 1)}, 8, 1, LIGHTGRAY);
        y += 12;

        // Morale bar
        DrawTextEx(GetFontDefault(), "Morale:", {(float)ix, (float)y}, fs, 1, LIGHTGRAY); y += lh;
        Color mc = e->morale >= 70 ? Color{50, 200, 50, 255} :
                   e->morale >= 40 ? Color{220, 180, 0, 255} : Color{220, 50, 50, 255};
        draw_stat_bar(ix, y, bar_w, 8, e->morale, mc, {40, 20, 20, 255});
        DrawTextEx(GetFontDefault(), (std::to_string(e->morale) + "%").c_str(),
                   {(float)(panel_x + panel_w - 32), (float)(y - 1)}, 8, 1, LIGHTGRAY);
        y += 12;

        // Supplies bar
        DrawTextEx(GetFontDefault(), "Supplies:", {(float)ix, (float)y}, fs, 1, LIGHTGRAY); y += lh;
        Color sc = e->supplies >= 60 ? Color{50, 120, 220, 255} :
                   e->supplies >= 30 ? Color{220, 140, 50, 255} : Color{220, 50, 50, 255};
        draw_stat_bar(ix, y, bar_w, 8, e->supplies, sc, {20, 20, 50, 255});
        DrawTextEx(GetFontDefault(), (std::to_string(e->supplies) + "%").c_str(),
                   {(float)(panel_x + panel_w - 32), (float)(y - 1)}, 8, 1, LIGHTGRAY);
        y += 12;

        y += 4;
        std::string mov = "Movement: " + std::to_string(e->movement_points) +
                          " / " + std::to_string(e->max_movement);
        DrawTextEx(GetFontDefault(), mov.c_str(), {(float)ix, (float)y}, fs, 1, WHITE); y += lh;

        if (!orders_s.empty()) {
            y += 4;
            DrawTextEx(GetFontDefault(), "Orders:", {(float)ix, (float)y}, fs, 1, YELLOW); y += lh;
            draw_wrapped_text(ix, y, bar_w, orders_s, 9, LIGHTGRAY);
        }
    }

    // ── Entity List Overlay ───────────────────────────────────────────────────

    void draw_entity_list_overlay() {
        if (!show_entity_list || !current_entity_data) return;

        std::vector<PositionedEntity*> valid;
        for (int i = 0; i < current_num_entities; ++i) {
            PositionedEntity* e = &current_entity_data[i];
            if (strlen(e->name.data()) > 0 &&
                std::string(e->name.data()).find("__") != 0) {
                valid.push_back(e);
            }
        }

        int row_h   = 16;
        int panel_w = 580;
        int hdr_h   = 30;
        int panel_h = hdr_h + row_h + 6 + (int)valid.size() * row_h + 16;
        int panel_x = (width - panel_w) / 2;
        int panel_y = (height - panel_h) / 2;

        DrawRectangle(panel_x, panel_y, panel_w, panel_h, {10, 10, 30, 235});
        DrawRectangleLines(panel_x, panel_y, panel_w, panel_h, {140, 140, 200, 255});

        DrawRectangle(panel_x, panel_y, panel_w, hdr_h, {30, 30, 80, 255});
        DrawTextEx(GetFontDefault(), "Entity Overview  [I to close | click row to select]",
                   {(float)(panel_x + 10), (float)(panel_y + 8)}, 12, 1, WHITE);

        int y  = panel_y + hdr_h + 4;
        int fs = 9;

        // Column headers
        DrawTextEx(GetFontDefault(), "Type",     {(float)(panel_x +   8), (float)y}, fs, 1, LIGHTGRAY);
        DrawTextEx(GetFontDefault(), "Name",     {(float)(panel_x +  80), (float)y}, fs, 1, LIGHTGRAY);
        DrawTextEx(GetFontDefault(), "House",    {(float)(panel_x + 200), (float)y}, fs, 1, LIGHTGRAY);
        DrawTextEx(GetFontDefault(), "Pos",      {(float)(panel_x + 310), (float)y}, fs, 1, LIGHTGRAY);
        DrawTextEx(GetFontDefault(), "Mo/Su/Eq", {(float)(panel_x + 370), (float)y}, fs, 1, LIGHTGRAY);
        DrawTextEx(GetFontDefault(), "Soldiers", {(float)(panel_x + 460), (float)y}, fs, 1, LIGHTGRAY);
        DrawTextEx(GetFontDefault(), "Orders",   {(float)(panel_x + 510), (float)y}, fs, 1, LIGHTGRAY);
        y += row_h;
        DrawLine(panel_x + 5, y - 2, panel_x + panel_w - 5, y - 2, {80, 80, 120, 200});

        for (PositionedEntity* e : valid) {
            std::string type_s    = get_entity_type_name(static_cast<EntityType>(e->entity_type));
            std::string name_s    = std::string(e->name.data());
            std::string house_s   = std::string(e->house_name.data());
            std::string orders_s  = std::string(e->orders.data());
            Color ec = {e->color[0], e->color[1], e->color[2], 255};
            std::string pos_s  = "(" + std::to_string(e->q) + "," + std::to_string(e->r) + ")";
            std::string stat_s = std::to_string(e->morale) + "/" +
                                 std::to_string(e->supplies) + "/" +
                                 std::to_string(e->equipment_level);
            std::string sol_s  = e->assigned_soldiers > 0 ? std::to_string(e->assigned_soldiers) : "-";
            // Truncate orders for display
            std::string ord_trunc = orders_s.size() > 8 ? orders_s.substr(0, 7) + "…" : orders_s;

            DrawTextEx(GetFontDefault(), type_s.c_str(),     {(float)(panel_x +   8), (float)y}, fs, 1, ec);
            DrawTextEx(GetFontDefault(), name_s.c_str(),     {(float)(panel_x +  80), (float)y}, fs, 1, WHITE);
            DrawTextEx(GetFontDefault(), house_s.c_str(),    {(float)(panel_x + 200), (float)y}, fs, 1, LIGHTGRAY);
            DrawTextEx(GetFontDefault(), pos_s.c_str(),      {(float)(panel_x + 310), (float)y}, fs, 1, LIGHTGRAY);
            DrawTextEx(GetFontDefault(), stat_s.c_str(),     {(float)(panel_x + 370), (float)y}, fs, 1, LIGHTGRAY);
            DrawTextEx(GetFontDefault(), sol_s.c_str(),      {(float)(panel_x + 460), (float)y}, fs, 1, LIGHTGRAY);
            DrawTextEx(GetFontDefault(), ord_trunc.c_str(),  {(float)(panel_x + 510), (float)y}, fs, 1, {180, 180, 100, 255});
            y += row_h;
        }
    }

    // Row click in the entity list overlay ("click row to select").
    // Returns true if the click landed on the overlay (consumed).
    bool check_entity_list_click(float mouse_x, float mouse_y) {
        if (!show_entity_list || !current_entity_data) return false;

        // Same entity filter and panel geometry as draw_entity_list_overlay
        std::vector<int> valid;
        for (int i = 0; i < current_num_entities; ++i) {
            PositionedEntity* e = &current_entity_data[i];
            if (strlen(e->name.data()) > 0 &&
                std::string(e->name.data()).find("__") != 0) {
                valid.push_back(i);
            }
        }

        int row_h   = 16;
        int panel_w = 580;
        int hdr_h   = 30;
        int panel_h = hdr_h + row_h + 6 + (int)valid.size() * row_h + 16;
        int panel_x = (width - panel_w) / 2;
        int panel_y = (height - panel_h) / 2;

        if (mouse_x < panel_x || mouse_x > panel_x + panel_w ||
            mouse_y < panel_y || mouse_y > panel_y + panel_h) {
            return false;
        }

        int first_row_y = panel_y + hdr_h + 4 + row_h;
        int row = (int)((mouse_y - first_row_y) / row_h);
        if (mouse_y >= first_row_y && row >= 0 && row < (int)valid.size()) {
            selected_entity_index = valid[row];
            show_entity_list = false;  // close overlay to reveal the inspector
        }
        return true;
    }

    bool check_house_panel_click(float mouse_x, float mouse_y) {
        int panel_width = 200;
        int collapsed_height = 30;
        int expanded_height = 120;
        int margin = 10;
        
        for (int i = 0; i < (int)house_panels_expanded.size(); ++i) {
            // Calculate panel position (same logic as in draw_house_info)
            int panel_x = margin;
            int panel_y = margin + i * (collapsed_height + margin);
            if (i > 0) {
                // Adjust for expanded panels above
                for (int j = 0; j < i; ++j) {
                    if (house_panels_expanded[j]) {
                        panel_y += (expanded_height - collapsed_height);
                    }
                }
            }
            
            // Check if click is within the header area of this panel
            if (mouse_x >= panel_x && mouse_x <= panel_x + panel_width &&
                mouse_y >= panel_y && mouse_y <= panel_y + 25) {
                house_panels_expanded[i] = !house_panels_expanded[i];
                return true;
            }
        }
        return false;
    }

    void draw_house_info(House* house_data, int num_houses) {
        int panel_width = 200;
        int collapsed_height = 30;
        int expanded_height = 120;
        int margin = 10;
        int header_font_size = 12;
        int body_font_size = 10;
        
        for (int i = 0; i < num_houses; ++i) {
            House* house = &house_data[i];
            
            // Parse house name properly (in case it contains encoded city info)
            std::string house_name_field = std::string(house->name.data());
            std::string display_name;
            
            if (has_encoded_city_name(house_name_field)) {
                display_name = extract_original_owner(house_name_field);
            } else {
                display_name = house_name_field;
            }
            
            // Calculate panel position and size
            int panel_x = margin;
            int panel_height = house_panels_expanded[i] ? expanded_height : collapsed_height;
            int panel_y = margin + i * (collapsed_height + margin);
            if (i > 0) {
                // Adjust for expanded panels above
                for (int j = 0; j < i; ++j) {
                    if (house_panels_expanded[j]) {
                        panel_y += (expanded_height - collapsed_height);
                    }
                }
            }
            
            // Draw background panel with house color
            Color house_color = {house->color[0], house->color[1], house->color[2], house->color[3]};
            Color panel_bg = {house_color.r, house_color.g, house_color.b, 40}; // Semi-transparent
            Color panel_border = {house_color.r, house_color.g, house_color.b, 180};
            
            // Background panel
            DrawRectangle(panel_x, panel_y, panel_width, panel_height, panel_bg);
            DrawRectangleLines(panel_x, panel_y, panel_width, panel_height, panel_border);
            
            // House name header with colored background (always visible)
            DrawRectangle(panel_x, panel_y, panel_width, 25, panel_border);
            std::string header_text = "House " + display_name + (house_panels_expanded[i] ? " ▼" : " ▶");
            DrawTextEx(GetFontDefault(), header_text.c_str(),
                      {(float)(panel_x + 8), (float)(panel_y + 5)}, header_font_size, 1, WHITE);
            // Raven badge
            if (house->ravens_in_transit > 0) {
                std::string rb = "[R:" + std::to_string(house->ravens_in_transit) + "]";
                DrawTextEx(GetFontDefault(), rb.c_str(),
                           {(float)(panel_x + panel_width - 40), (float)(panel_y + 6)}, 9, 1, {180, 220, 255, 255});
            }
            // War badge
            if (house->at_war > 0) {
                std::string wb = "[WAR]";
                float war_x = house->ravens_in_transit > 0 ? panel_x + panel_width - 75.0f : panel_x + panel_width - 44.0f;
                DrawTextEx(GetFontDefault(), wb.c_str(),
                           {war_x, (float)(panel_y + 6)}, 9, 1, {255, 80, 80, 255});
            }
            
            // Only draw detailed info if expanded
            if (house_panels_expanded[i]) {
                // Population and loyalty section
                int text_y = panel_y + 30;
                std::string pop_info = "Pop: " + std::to_string(house->population);
                DrawTextEx(GetFontDefault(), pop_info.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, BLACK);
                
                text_y += 12;
                std::string loyalty_info = "Loyalty: " + std::to_string(house->population_loyalty) + "%";
                Color loyalty_color = house->population_loyalty >= 80 ? GREEN : 
                                     house->population_loyalty >= 50 ? ORANGE : RED;
                DrawTextEx(GetFontDefault(), loyalty_info.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, loyalty_color);
                
                text_y += 12;
                std::string military_info = "Military: " + std::to_string(house->military_power);
                DrawTextEx(GetFontDefault(), military_info.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, BLACK);
                
                // Resources section
                text_y += 15;
                std::string resources = "F:" + std::to_string(static_cast<int>(house->food)) + 
                                       " M:" + std::to_string(static_cast<int>(house->material)) +
                                       " I:" + std::to_string(static_cast<int>(house->metal)) +
                                       " G:" + std::to_string(static_cast<int>(house->gold));
                DrawTextEx(GetFontDefault(), resources.c_str(), {(float)(panel_x + 8), (float)text_y}, body_font_size, 1, BLACK);
            }
        }
    }

    void handle_input(const std::unordered_map<std::pair<int,int>, HexTile*>& shared_tile_map) {
        if (IsKeyDown(KEY_A)) camera.target.x -= 10 / camera.zoom;
        if (IsKeyDown(KEY_D)) camera.target.x += 10 / camera.zoom;
        if (IsKeyDown(KEY_S)) camera.target.y += 10 / camera.zoom;
        if (IsKeyDown(KEY_W)) camera.target.y -= 10 / camera.zoom;

        if (IsKeyPressed(KEY_T)) show_territory = !show_territory;
        if (IsKeyPressed(KEY_R)) show_resources = !show_resources;
        if (IsKeyPressed(KEY_I)) show_entity_list = !show_entity_list;
        if (IsKeyPressed(KEY_M)) show_minimap = !show_minimap;
        if (IsKeyPressed(KEY_L)) show_event_log = !show_event_log;
        if (IsKeyPressed(KEY_Y)) show_turn_stats = !show_turn_stats;
        if (IsKeyPressed(KEY_C)) {
            show_chat = !show_chat;
            if (show_chat) chat_follow = true;  // snap to latest on open
        }
        if (IsKeyPressed(KEY_F11)) ToggleBorderlessWindowed();
        if (IsKeyPressed(KEY_ESCAPE)) {
            if (show_chat) { show_chat = false; }
            else { selected_entity_index = -1; show_entity_list = false; }
        }

        // Chat inspector navigation (only while open)
        if (show_chat) {
            int num_agents = 0;
            if (agents_raw != MAP_FAILED)
                num_agents = *static_cast<int*>(agents_raw);
            if (IsKeyPressed(KEY_DOWN) && chat_agent_index < num_agents - 1) {
                chat_agent_index++; chat_scroll = 0; chat_follow = true;
            }
            if (IsKeyPressed(KEY_UP) && chat_agent_index > 0) {
                chat_agent_index--; chat_scroll = 0; chat_follow = true;
            }
            if (IsKeyPressed(KEY_PAGE_DOWN)) { chat_scroll += 20; chat_follow = false; }
            if (IsKeyPressed(KEY_PAGE_UP)) { chat_scroll -= 20; chat_follow = false; }
            if (chat_scroll < 0) chat_scroll = 0;
            if (IsKeyPressed(KEY_END)) chat_follow = true;
        }

        // Left click: entity list overlay first, then house panel, then entity select.
        // Suppressed while the chat inspector overlay is open.
        if (IsMouseButtonPressed(MOUSE_LEFT_BUTTON) && !show_chat) {
            Vector2 mouse_pos = GetMousePosition();
            if (!check_entity_list_click(mouse_pos.x, mouse_pos.y) &&
                !check_house_panel_click(mouse_pos.x, mouse_pos.y)) {
                check_entity_click(mouse_pos.x, mouse_pos.y, shared_tile_map);
            }
        }

        float wheel = GetMouseWheelMove();
        if (wheel != 0 && show_chat) {
            // While the chat inspector is open, the wheel scrolls chat
            // instead of zooming the map
            chat_scroll -= (int)(wheel * 3);
            if (chat_scroll < 0) chat_scroll = 0;
            chat_follow = false;
        } else if (wheel != 0) {
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
        .def("run", &HexGridRenderer::run, py::call_guard<py::gil_scoped_release>(), 
             py::arg("shared_memory_name"), py::arg("memory_size"), py::arg("num_tiles"),
             py::arg("house_shared_memory_name"), py::arg("house_memory_size"), py::arg("num_houses"),
             py::arg("entities_shared_memory_name") = nullptr, py::arg("entities_memory_size") = 0, 
             py::arg("num_entities") = 0) 
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