# Extensible Shared Memory System Guide

## Overview
This guide documents how to extend the feudal simulation's shared memory rendering system to add new visual elements without breaking existing code.

## Core Principle
Instead of modifying the rigid C++ structs and Python dtypes, we **reuse existing fields** as metadata carriers and add helper functions to encode/decode additional information.

## Step-by-Step Extension Process

### 1. Identify Extension Point
Look for existing fields that can be repurposed:
- Numeric fields with unused value ranges (e.g., `metal_output > 100`)
- String fields with unused space
- Array fields with unused indices

### 2. Create Python Extension Module
Create a helper module (e.g., `tile_extensions.py`) with:

```python
# Define your new data types
class ResourceNodeType(Enum):
    NONE = 0
    GOLD_MINE = 1 
    IRON_DEPOSIT = 2
    # Add more as needed

# Encoding functions
def set_resource_node(tile: HexTile, node_type: ResourceNodeType) -> None:
    # Encode into existing field
    if node_type == ResourceNodeType.NONE:
        # Preserve original value
        if tile.metal_output > 100:
            tile.metal_output = tile.metal_output % 100
    else:
        # Encode: 100 + type + original_value
        original = tile.metal_output % 100 if tile.metal_output > 100 else tile.metal_output
        tile.metal_output = 100 + node_type.value + (original / 100)

# Decoding functions  
def get_resource_node_type(tile: HexTile) -> ResourceNodeType:
    if tile.metal_output > 100:
        resource_code = int(tile.metal_output) - 100
        try:
            return ResourceNodeType(resource_code)
        except ValueError:
            return ResourceNodeType.NONE
    return ResourceNodeType.NONE

# Convenience functions
def add_gold_mine(tile: HexTile) -> None:
    set_resource_node(tile, ResourceNodeType.GOLD_MINE)

def get_base_metal_output(tile: HexTile) -> float:
    """Get original value excluding encoding"""
    if tile.metal_output > 100:
        return tile.metal_output % 100
    return tile.metal_output
```

### 3. Update C++ Renderer
Add corresponding C++ code to decode and visualize:

```cpp
// Mirror the Python enum
enum class ResourceNodeType {
    NONE = 0,
    GOLD_MINE = 1,
    IRON_DEPOSIT = 2
};

// Add visual definitions
std::map<ResourceNodeType, Color> resource_colors = {
    {ResourceNodeType::GOLD_MINE, Color{255, 215, 0, 200}},
    {ResourceNodeType::IRON_DEPOSIT, Color{169, 169, 169, 200}}
};

// Decoding functions (must match Python logic exactly)
ResourceNodeType get_resource_node_type(const HexTile& tile) {
    if (tile.metal_output > 100) {
        int resource_code = static_cast<int>(tile.metal_output) - 100;
        if (resource_code >= 1 && resource_code <= 2) {
            return static_cast<ResourceNodeType>(resource_code);
        }
    }
    return ResourceNodeType::NONE;
}

// Update rendering function
void draw_tile(const HexTile& tile) {
    // ... existing tile rendering ...
    
    // Add new visualization
    if (show_resources && has_special_resource(tile)) {
        draw_resource_node(tile, x, y);
    }
}

void draw_resource_node(const HexTile& tile, float x, float y) {
    ResourceNodeType resource_type = get_resource_node_type(tile);
    if (resource_type == ResourceNodeType::NONE) return;

    // Draw visual indicator
    Color resource_color = resource_colors[resource_type];
    float radius = tile_size * 0.3f;
    DrawCircle(x, y, radius, resource_color);
    
    // Add symbol/text if desired
    if (tile_size > 20) {
        std::string symbol = get_resource_symbol(resource_type);
        DrawText(symbol.c_str(), x, y, font_size, BLACK);
    }
}
```

### 4. Add Integration Code
Update your simulation to use the new features:

```python
# In simulation initialization
def add_resource_nodes(self):
    land_tiles = [tile for tile in self.hex_grid.tiles if self.hex_grid.is_land(tile)]
    selected_tiles = random.sample(land_tiles, num_resources)
    
    for i, tile in enumerate(selected_tiles):
        if i % 2 == 0:
            add_gold_mine(tile)
        else:
            add_iron_deposit(tile)
```

### 5. Add User Controls (Optional)
```cpp
// In handle_input()
if (IsKeyPressed(KEY_R)) {
    show_resources = !show_resources;
}

// In tile info display
if (has_special_resource(*tile)) {
    ResourceNodeType type = get_resource_node_type(*tile);
    info += "\nSpecial Resource: " + get_resource_name(type);
}
```

## Key Requirements

### ✅ **Must Do:**
- Keep encoding/decoding logic **identical** between Python and C++
- Test edge cases (what happens with invalid values?)
- Preserve backward compatibility
- Document the encoding scheme clearly

### ❌ **Never Do:**
- Modify core struct definitions in `renderer.cpp`
- Change shared memory layout or sizes
- Break existing functionality
- Assume unused fields will stay unused forever

## Encoding Schemes

### Numeric Field Encoding
```
Original range: 0-99
Extended range: 100+ for special data
Encoding: 100 + type_id + (original_value / 100)
```

### String Field Encoding  
```
Use special prefixes: "SPECIAL:type:data"
Or suffix encoding: "original_name#type#data"
```

### Array Field Encoding
```python
# Use unused array indices
tile.owner_color[3] = special_type_id  # Alpha channel for metadata
```

## Testing Checklist

- [ ] Original functionality unchanged
- [ ] New features work as expected  
- [ ] No memory corruption or crashes
- [ ] Python/C++ encoding matches exactly
- [ ] Edge cases handled gracefully
- [ ] Performance impact minimal

## Benefits of This Approach

1. **No Breaking Changes**: Existing code continues to work
2. **Fast Development**: No complex migrations needed
3. **Easy Iteration**: Add/remove features quickly
4. **Backward Compatible**: Old saves/data still work
5. **Minimal Risk**: Limited scope of changes

## When NOT to Use This Approach

- When you need many new fields (consider struct versioning instead)
- When encoding becomes too complex or fragile
- When performance is critical and decoding overhead matters
- When the extension doesn't fit well into existing field semantics

## Example Extensions You Could Add

- **Terrain modifiers**: Use `elevation` field encoding
- **Building types**: Use `population_capacity` encoding  
- **Road networks**: Use `owner` string encoding
- **Seasonal effects**: Use `temperature` field encoding
- **Unit positions**: Use `moisture` field encoding

Each follows the same pattern: encode in existing field, add helper functions, update renderer.