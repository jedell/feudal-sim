# Shared Memory Extensibility Example

## Current Pain Point
Adding new fields to HexTile requires:
1. Updating C++ struct in renderer.cpp
2. Updating Python dtype in hex_grid.py  
3. Updating data marshaling code
4. Ensuring exact size alignment

## Simple Solution: Reserved Fields
Instead of changing the core struct, add reserved fields that can be repurposed.

## Example: Adding Resource Nodes

Let's say we want to add "resource_node_type" to tiles for special resources like gold mines.

### Current Approach (Brittle):
- Modify HexTile struct
- Update 4 different files
- Risk breaking memory alignment

### Better Approach (Extensible):
- Use existing field as metadata
- Add helper functions for interpretation
- Keep backward compatibility

This example shows how to add the feature using the existing `metal_output` field as a resource indicator.